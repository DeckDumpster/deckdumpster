#!/usr/bin/env bash
#
# Find and remove orphaned MTGC instance artifacts on this host:
# image tags, data volumes, Quadlet units, env files, and timer units.
#
# An "orphan" is any candidate instance name that:
#   - is NOT in the protected list (default: "prod"), AND
#   - has NO currently-running container.
#
# Usage:
#   bash deploy/prune-instances.sh --dry-run    # preview, no changes
#   bash deploy/prune-instances.sh              # apply
#
# Override the protected list with MTGC_PROTECT_INSTANCES (space-separated):
#   MTGC_PROTECT_INSTANCES="prod staging" bash deploy/prune-instances.sh
#
# Safe to run while other instances are active — the running-container
# check protects them. Always run --dry-run first if unsure.

set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

PROTECTED="${MTGC_PROTECT_INSTANCES:-prod}"

is_protected() {
    for p in $PROTECTED; do
        [ "$1" = "$p" ] && return 0
    done
    return 1
}

is_running() {
    [ "$(podman inspect -f '{{.State.Running}}' "systemd-mtgc-$1" 2>/dev/null)" = "true" ]
}

# --- Discover candidate instance names from every artifact location ---

declare -A CANDIDATES

# Image tags: localhost/mtgc:<instance>  (skip "latest" — that's the rolling alias)
while IFS= read -r tag; do
    inst="${tag#localhost/mtgc:}"
    [ "$inst" = "latest" ] && continue
    CANDIDATES["$inst"]=1
done < <(podman images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -E '^localhost/mtgc:' || true)

# Volumes: mtgc-<instance>-data
while IFS= read -r vol; do
    [[ "$vol" =~ ^mtgc-(.+)-data$ ]] || continue
    CANDIDATES["${BASH_REMATCH[1]}"]=1
done < <(podman volume ls --format '{{.Name}}' 2>/dev/null || true)

# Quadlet container units
for f in "$HOME/.config/containers/systemd/mtgc-"*.container; do
    [ -f "$f" ] || continue
    base="$(basename "$f" .container)"
    CANDIDATES["${base#mtgc-}"]=1
done

# Per-instance env files (skip default.env, which is the shared template)
for f in "$HOME/.config/mtgc/"*.env; do
    [ -f "$f" ] || continue
    name="$(basename "$f" .env)"
    [ "$name" = "default" ] && continue
    CANDIDATES["$name"]=1
done

# Timer units (prices/sealed-catalog/backup/edhrec, one of each per instance)
for f in "$HOME/.config/systemd/user/mtgc-"*.timer; do
    [ -f "$f" ] || continue
    base="$(basename "$f" .timer)"
    for role in prices sealed-catalog backup edhrec; do
        prefix="mtgc-${role}-"
        case "$base" in
            "${prefix}"*) CANDIDATES["${base#${prefix}}"]=1 ;;
        esac
    done
done

# --- Classify each candidate ---

ORPHANS=()
KEPT=()
for inst in "${!CANDIDATES[@]}"; do
    if is_protected "$inst"; then
        KEPT+=("$inst (protected)")
    elif is_running "$inst"; then
        KEPT+=("$inst (running)")
    else
        ORPHANS+=("$inst")
    fi
done

# --- Report ---

echo "=== MTGC instance audit ==="
echo "Protected: $PROTECTED"
echo
if [ "${#KEPT[@]}" -gt 0 ]; then
    echo "Keeping:"
    printf "  - %s\n" "${KEPT[@]}"
    echo
fi
if [ "${#ORPHANS[@]}" -eq 0 ]; then
    echo "No orphans found. Nothing to do."
    exit 0
fi
echo "Orphans:"
printf "  - %s\n" "${ORPHANS[@]}"
echo

if [ "$DRY_RUN" = "true" ]; then
    echo "(dry-run) No changes made. Re-run without --dry-run to apply."
    exit 0
fi

# --- Remove each orphan's artifacts ---
#
# Inlined rather than calling teardown.sh because teardown.sh requires the
# Quadlet to exist; partial-state orphans (e.g. Quadlet already removed but
# image+timer still around) would make it bail.

for inst in "${ORPHANS[@]}"; do
    echo "==> Removing $inst..."

    # Stop and remove role timers (prices, sealed-catalog, backup, edhrec)
    for ROLE in prices sealed-catalog backup edhrec; do
        systemctl --user stop "mtgc-${ROLE}-${inst}.timer" 2>/dev/null || true
        systemctl --user disable "mtgc-${ROLE}-${inst}.timer" 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/mtgc-${ROLE}-${inst}.service" \
              "$HOME/.config/systemd/user/mtgc-${ROLE}-${inst}.timer"
    done

    # Stop main service and remove Quadlet
    systemctl --user stop "mtgc-${inst}" 2>/dev/null || true
    systemctl --user disable "mtgc-${inst}" 2>/dev/null || true
    rm -f "$HOME/.config/containers/systemd/mtgc-${inst}.container"

    # Remove image tag, data volume, and env file
    podman rmi "mtgc:${inst}" 2>/dev/null || true
    podman volume rm "mtgc-${inst}-data" 2>/dev/null || true
    rm -f "$HOME/.config/mtgc/${inst}.env"

    echo "    Done."
done

systemctl --user daemon-reload
echo
echo "==> Removed ${#ORPHANS[@]} orphan instance(s)."
