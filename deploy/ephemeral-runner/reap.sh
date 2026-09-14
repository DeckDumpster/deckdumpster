#!/usr/bin/env bash
#
# Destroy every ephemeral runner VM older than N hours.
# This is the bead's most important script: if: always() does not cover a
# run GitHub drops, a cancellation landing between clone and output, or the
# hypervisor rebooting mid-run. Without a reaper those become a hypervisor
# full of dead clones, discovered as a storage-full alert weeks later with
# no way to tell which clones are live.
#
# Usage:
#   reap.sh [--max-age-hours N] [--dry-run]
#
# --dry-run prints what it would destroy and touches nothing. This is the
# behaviour a human gets when they run it wrong, so it must be the first
# thing to type when the ledger looks suspicious.
#
# Age preference: ledger epoch is authoritative. Falls back to the creation
# timestamp in `qm config`'s meta section for a VM whose ledger line was
# lost — the lost-ledger case is exactly the one that produces orphans, so
# falling back rather than skipping is the correct tradeoff.
#
# Environment variables:
#   TEMPLATE_VMID — source VM template id (default: 101); never reaped.
#   LEDGER_FILE   — active-runner ledger path
#                   (default: /var/lib/gh-ephemeral-runner/active)
#
set -euo pipefail

TEMPLATE_VMID="${TEMPLATE_VMID:-101}"
LEDGER_FILE="${LEDGER_FILE:-/var/lib/gh-ephemeral-runner/active}"
MAX_AGE_HOURS=4
DRY_RUN=false

while [ $# -gt 0 ]; do
    case $1 in
        --max-age-hours)
            if [ $# -lt 2 ] || ! [[ "$2" =~ ^[0-9]+$ ]]; then
                echo "reap.sh: --max-age-hours requires a positive integer" >&2
                exit 1
            fi
            MAX_AGE_HOURS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Usage: reap.sh [--max-age-hours N] [--dry-run]" >&2
            exit 1
            ;;
    esac
done

NOW="$(date +%s)"
CUTOFF=$(( NOW - MAX_AGE_HOURS * 3600 ))

if "$DRY_RUN"; then
    echo "reap.sh: DRY RUN — max-age-hours=$MAX_AGE_HOURS cutoff=$(date -d "@$CUTOFF" --iso-8601=seconds 2>/dev/null || date -r "$CUTOFF" '+%Y-%m-%dT%H:%M:%S')" >&2
fi

# Collect all VMIDs named gh-runner-* from Proxmox.
# qm list output format: VMID NAME STATUS ...
# We select only lines whose name column starts with gh-runner-.
mapfile -t RUNNER_VMIDS < <(
    qm list --full 2>/dev/null \
    | awk 'NR>1 && $2 ~ /^gh-runner-/ {print $1}'
)

if [ "${#RUNNER_VMIDS[@]}" -eq 0 ]; then
    echo "reap.sh: no gh-runner-* VMs found on host" >&2
    exit 0
fi

reaped=0
skipped=0

for VMID in "${RUNNER_VMIDS[@]}"; do
    # Never touch the template, even if it were somehow named gh-runner-*.
    if [ "$VMID" -eq "$TEMPLATE_VMID" ]; then
        echo "reap.sh: skipping template VMID $TEMPLATE_VMID" >&2
        (( skipped++ )) || true
        continue
    fi

    # Determine age. Prefer the ledger's recorded epoch.
    LEDGER_EPOCH=""
    if [ -f "$LEDGER_FILE" ]; then
        LEDGER_EPOCH="$(awk -v id="$VMID" '$1 == id {print $3; exit}' "$LEDGER_FILE")"
    fi

    if [ -n "$LEDGER_EPOCH" ] && [[ "$LEDGER_EPOCH" =~ ^[0-9]+$ ]]; then
        VM_EPOCH="$LEDGER_EPOCH"
        AGE_SOURCE="ledger"
    else
        # Fall back to qm config meta/creation. The field looks like:
        #   meta: creation=1726300000,...
        META="$(qm config "$VMID" 2>/dev/null | awk -F'creation=' '/^meta:/{split($2,a,","); print a[1]}')"
        if [ -n "$META" ] && [[ "$META" =~ ^[0-9]+$ ]]; then
            VM_EPOCH="$META"
            AGE_SOURCE="qm-config"
        else
            # Cannot determine age — reaped conservatively: if the ledger is
            # missing and qm config has no creation stamp, the VM is a genuine
            # orphan with unknown age. Reap it.
            echo "reap.sh: VM $VMID has no age record (ledger miss + no meta); treating as orphan" >&2
            AGE_SOURCE="orphan"
            VM_EPOCH=0
        fi
    fi

    AGE_SECONDS=$(( NOW - VM_EPOCH ))
    AGE_HOURS=$(( AGE_SECONDS / 3600 ))

    if [ "$VM_EPOCH" -gt "$CUTOFF" ]; then
        echo "reap.sh: VM $VMID ($AGE_SOURCE) is ${AGE_HOURS}h old — keeping" >&2
        (( skipped++ )) || true
        continue
    fi

    if "$DRY_RUN"; then
        echo "reap.sh: DRY RUN — would destroy VM $VMID ($AGE_SOURCE, ${AGE_HOURS}h old)" >&2
        (( reaped++ )) || true
        continue
    fi

    echo "reap.sh: destroying VM $VMID ($AGE_SOURCE, ${AGE_HOURS}h old)" >&2

    # Stop first; ignore failure (VM may already be stopped or in error state).
    qm stop "$VMID" --timeout 30 >&2 || true
    qm destroy "$VMID" --purge >&2

    # Remove from ledger.
    if [ -f "$LEDGER_FILE" ]; then
        sed -i "/^${VMID} /d" "$LEDGER_FILE"
    fi

    echo "reap.sh: VM $VMID destroyed" >&2
    (( reaped++ )) || true
done

if "$DRY_RUN"; then
    echo "reap.sh: DRY RUN complete — would destroy $reaped VM(s), skip $skipped" >&2
else
    echo "reap.sh: done — destroyed $reaped VM(s), kept $skipped" >&2
fi
