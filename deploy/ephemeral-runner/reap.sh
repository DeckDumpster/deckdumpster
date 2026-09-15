#!/usr/bin/env bash
#
# Destroy every ephemeral runner VM that is old enough and confirmed idle.
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
# Destruction requires two confirmations:
#   1. The VM must be old enough (ledger epoch or Proxmox config ctime).
#   2. The GitHub busy check must show the runner is not live.
# A VM that fails either check is SKIPPED. An unknown age is a refusal, not
# a licence: VM_EPOCH=0 resolves to 1970, making every VM past the cutoff
# regardless of reality. "I cannot tell how old this is" must mean skip.
#
# Transport: Proxmox HTTP API with an API token, not the qm CLI. The pveum
# grant is scoped to /pool/ephemeral-ci so the token can only see the
# template and live clones, not any other VMs on the host. GET /nodes/qemu
# returns an HTTP status, so a failure is never misread as an empty list.
#
# Age source preference: ledger epoch (authoritative). Falls back to the
# ctime field in the Proxmox config API for a VM whose ledger line was lost.
# The real Proxmox meta string (host-verified 2026-09-14):
#   meta: creation-qemu=11.0.0,ctime=1789270996
# ctime= is the epoch. creation-qemu= is the QEMU version string, not a
# timestamp, so awk -F'creation=' was dead code — the next char after
# 'creation' is '-', not '=', so the field separator never matched.
#
# Environment variables (required for live use):
#   PVE_NODE         — Proxmox node name (e.g. "pve")
#   PVE_TOKEN_ID     — Proxmox API token id (user@realm!tokenname)
#   PVE_TOKEN_SECRET — Proxmox API token secret
#   GITHUB_TOKEN     — GitHub API token (for runner busy check)
#   GH_REPO          — GitHub repository, owner/repo form
#
# Optional:
#   PVE_API_HOST  — Proxmox API host (default: localhost)
#   PVE_API_PORT  — Proxmox API port (default: 8006)
#   TEMPLATE_VMID — source VM template id (default: 101); never reaped
#   LEDGER_FILE   — active-runner ledger path
#                   (default: /var/lib/gh-ephemeral-runner/active)
#   CRED_FILE     — credential file to source (default:
#                   /etc/gh-ephemeral-runner/token); sourced before the
#                   defaults below so TEMPLATE_VMID set there overrides the
#                   compiled-in default of 101.
#
set -euo pipefail

CRED_FILE="${CRED_FILE:-/etc/gh-ephemeral-runner/token}"
if [ -f "$CRED_FILE" ]; then
    # shellcheck source=/dev/null
    . "$CRED_FILE"
fi

TEMPLATE_VMID="${TEMPLATE_VMID:-101}"
LEDGER_FILE="${LEDGER_FILE:-/var/lib/gh-ephemeral-runner/active}"
SNIPPETS_DIR="${SNIPPETS_DIR:-/var/lib/vz/snippets}"
PVE_NODE="${PVE_NODE:-}"
PVE_API_HOST="${PVE_API_HOST:-localhost}"
PVE_API_PORT="${PVE_API_PORT:-8006}"
PVE_TOKEN_ID="${PVE_TOKEN_ID:-}"
PVE_TOKEN_SECRET="${PVE_TOKEN_SECRET:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
GH_REPO="${GH_REPO:-}"

# MAX_AGE_HOURS must exceed the CI workflow's job timeout-minutes / 60.
# GitHub's own default job timeout is 360 min (6 h); until an explicit
# timeout-minutes is set on the build job, any job can run up to 6 h.
# The default here is 8 h (6 h + 2 h buffer) so the reaper never races a
# live build. When an explicit timeout-minutes lands on the build job, update
# this default to: ceil(timeout_minutes / 60) + 2.
MAX_AGE_HOURS=8
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

if [ -z "$PVE_NODE" ]; then
    echo "reap.sh: PVE_NODE is required" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Proxmox HTTP API wrapper
#
# Exits non-zero on HTTP 4xx/5xx (--fail) or connection error (--show-error).
# All response output goes to stdout; curl diagnostics go to stderr.
# ---------------------------------------------------------------------------
pvapi() {
    local method="$1" path="$2"
    shift 2
    curl --silent --fail --show-error \
        --request "$method" \
        --header "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" \
        --header "Accept: application/json" \
        "https://${PVE_API_HOST}:${PVE_API_PORT}/api2/json${path}" \
        "$@"
}

# ---------------------------------------------------------------------------
# GitHub runner busy check
#
# Returns 0 (true) if the runner named $1 is registered and currently busy.
# Returns 1 (false) if the runner is idle, absent, or the check cannot run.
#
# An ephemeral runner deregisters after its job completes, so "not found"
# is as safe a signal as "found and not busy" — both mean the job is done.
#
# When GITHUB_TOKEN or GH_REPO is unset, a warning is printed and the
# function returns 1 (not busy) so age-based reaping still works. This is
# a degraded mode: the busy-check is skipped and age is the only guard.
# Set both variables in production.
# ---------------------------------------------------------------------------
github_runner_busy() {
    local runner_name="$1"
    if [ -z "$GITHUB_TOKEN" ] || [ -z "$GH_REPO" ]; then
        echo "reap.sh: WARNING: GITHUB_TOKEN or GH_REPO not set; busy check skipped for $runner_name (degraded mode)" >&2
        return 1
    fi
    local response
    if ! response="$(
        curl --silent --fail --show-error \
            --header "Authorization: Bearer ${GITHUB_TOKEN}" \
            --header "Accept: application/vnd.github+json" \
            --header "X-GitHub-Api-Version: 2022-11-28" \
            "https://api.github.com/repos/${GH_REPO}/actions/runners?per_page=100" 2>&1
    )"; then
        echo "reap.sh: WARNING: GitHub API request failed; treating $runner_name as not busy" >&2
        return 1
    fi
    python3 - "$response" "$runner_name" <<'EOF'
import json, sys
try:
    for r in json.loads(sys.argv[1]).get("runners", []):
        if r.get("name") == sys.argv[2] and r.get("busy"):
            sys.exit(0)
except Exception as e:
    print(f"reap.sh: WARNING: could not parse GitHub response: {e}", file=sys.stderr)
sys.exit(1)
EOF
}

# ---------------------------------------------------------------------------
# Stop a VM via the Proxmox API and wait for it to reach the stopped state.
# Returns 0 when the VM is stopped; 1 on timeout (60 s).
# ---------------------------------------------------------------------------
vm_stop() {
    local vmid="$1"
    pvapi POST "/nodes/${PVE_NODE}/qemu/${vmid}/status/stop" >/dev/null 2>&1 || true
    local deadline=$(( $(date +%s) + 60 ))
    while true; do
        local vm_status
        vm_status="$(
            pvapi GET "/nodes/${PVE_NODE}/qemu/${vmid}/status/current" 2>/dev/null \
            | python3 -c "import json,sys; print(json.load(sys.stdin).get('data',{}).get('status',''))" 2>/dev/null
        )" || break
        [ "$vm_status" = "stopped" ] && return 0
        if [ "$(date +%s)" -ge "$deadline" ]; then
            echo "reap.sh: timeout waiting for VM $vmid to stop" >&2
            return 1
        fi
        sleep 2
    done
    return 1
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

NOW="$(date +%s)"
CUTOFF=$(( NOW - MAX_AGE_HOURS * 3600 ))

if "$DRY_RUN"; then
    echo "reap.sh: DRY RUN — max-age-hours=$MAX_AGE_HOURS cutoff=$(date -d "@$CUTOFF" --iso-8601=seconds 2>/dev/null || date -r "$CUTOFF" '+%Y-%m-%dT%H:%M:%S')" >&2
fi

# Enumerate runner VMs via the Proxmox API.
# A failure here is a hard error: we cannot reap safely if we cannot enumerate.
# The pveum grant is scoped to /pool/ephemeral-ci so this only sees the
# template and live clones; the gh-runner-* name filter is still required
# because the template itself is in the pool and must never be reaped.
QEMU_LIST=""
if ! QEMU_LIST="$(pvapi GET "/nodes/${PVE_NODE}/qemu")"; then
    echo "reap.sh: failed to enumerate VMs from Proxmox API" >&2
    exit 1
fi

mapfile -t RUNNER_VMIDS < <(
    python3 - "$QEMU_LIST" <<'EOF'
import json, sys
for vm in json.loads(sys.argv[1]).get("data", []):
    if vm.get("name", "").startswith("gh-runner-"):
        print(vm["vmid"])
EOF
)

if [ "${#RUNNER_VMIDS[@]}" -eq 0 ]; then
    echo "reap.sh: no gh-runner-* VMs visible to this token" >&2
    exit 0
fi

reaped=0
skipped=0
unknown_age=0

for VMID in "${RUNNER_VMIDS[@]}"; do
    # Never touch the template, even if it were somehow named gh-runner-*.
    if [ "$VMID" -eq "$TEMPLATE_VMID" ]; then
        echo "reap.sh: skipping template VMID $TEMPLATE_VMID" >&2
        (( skipped++ )) || true
        continue
    fi

    # Refuse any VM whose list entry carries template:1, regardless of
    # TEMPLATE_VMID. The id is configuration and can be wrong; the template
    # flag is a fact written by Proxmox when the VM was converted and cannot
    # be falsified by a misconfigured default.
    VM_IS_TEMPLATE="$(python3 - "$QEMU_LIST" "$VMID" <<'EOF'
import json, sys
for vm in json.loads(sys.argv[1]).get("data", []):
    if str(vm.get("vmid", "")) == sys.argv[2]:
        print(1 if vm.get("template") else 0)
        break
else:
    print(0)
EOF
)"
    if [ "${VM_IS_TEMPLATE:-0}" = "1" ]; then
        echo "reap.sh: skipping template VMID $VMID (template:1 in config)" >&2
        (( skipped++ )) || true
        continue
    fi

    # The VM name from the enumeration payload drives the GitHub busy check.
    VM_NAME="$(python3 - "$QEMU_LIST" "$VMID" <<'EOF'
import json, sys
for vm in json.loads(sys.argv[1]).get("data", []):
    if str(vm.get("vmid", "")) == sys.argv[2]:
        print(vm.get("name", ""))
        break
EOF
)"

    # --- Age determination ---
    # Prefer the ledger's recorded epoch (written by provision.sh at clone time).
    LEDGER_EPOCH=""
    if [ -f "$LEDGER_FILE" ]; then
        LEDGER_EPOCH="$(awk -v id="$VMID" '$1 == id {print $3; exit}' "$LEDGER_FILE")"
    fi

    VM_EPOCH=""
    AGE_SOURCE=""

    if [ -n "$LEDGER_EPOCH" ] && [[ "$LEDGER_EPOCH" =~ ^[0-9]+$ ]]; then
        VM_EPOCH="$LEDGER_EPOCH"
        AGE_SOURCE="ledger"
    else
        # Fall back to the ctime field in the Proxmox config API.
        # The Proxmox meta string looks like:
        #   creation-qemu=11.0.0,ctime=1789270996
        # The epoch is ctime=; creation-qemu= is the QEMU version (not a
        # timestamp). Reading from the API JSON avoids the original awk
        # field-separator bug where awk -F'creation=' never matched.
        VM_CONFIG=""
        if ! VM_CONFIG="$(pvapi GET "/nodes/${PVE_NODE}/qemu/${VMID}/config")"; then
            echo "reap.sh: VM $VMID ($VM_NAME): failed to read config; skipping" >&2
            (( skipped++ )) || true
            (( unknown_age++ )) || true
            continue
        fi
        META_EPOCH="$(python3 - "$VM_CONFIG" <<'EOF'
import json, sys, re
meta = json.loads(sys.argv[1]).get("data", {}).get("meta", "")
m = re.search(r"ctime=(\d+)", meta)
print(m.group(1) if m else "")
EOF
)"
        if [ -n "$META_EPOCH" ] && [[ "$META_EPOCH" =~ ^[0-9]+$ ]]; then
            VM_EPOCH="$META_EPOCH"
            AGE_SOURCE="qm-config"
        else
            # Neither the ledger nor the Proxmox config can give us an age.
            # Skipping is the only safe choice. VM_EPOCH=0 would resolve to
            # 1970, making this VM older than any cutoff and authorising
            # destruction with no evidence — which is exactly the defect this
            # replaces. An orphan that survives another hour costs disk; a
            # running build destroyed as an orphan costs a red CI run and an
            # hour of someone's confidence.
            echo "reap.sh: VM $VMID ($VM_NAME): no age record (ledger miss + no ctime in config); skipping" >&2
            (( skipped++ )) || true
            (( unknown_age++ )) || true
            continue
        fi
    fi

    AGE_SECONDS=$(( NOW - VM_EPOCH ))
    AGE_HOURS=$(( AGE_SECONDS / 3600 ))

    # --- Busy check ---
    # A runner deregisters from GitHub when its job finishes (--ephemeral),
    # so "not found" in the runners list is as safe as "found and not busy".
    # Only a "found AND busy" result protects the VM from the age check.
    if github_runner_busy "$VM_NAME"; then
        echo "reap.sh: VM $VMID ($VM_NAME, ${AGE_HOURS}h old): runner is busy — keeping" >&2
        (( skipped++ )) || true
        continue
    fi

    # --- Age check ---
    if [ "$VM_EPOCH" -gt "$CUTOFF" ]; then
        echo "reap.sh: VM $VMID ($VM_NAME, $AGE_SOURCE) is ${AGE_HOURS}h old — keeping" >&2
        (( skipped++ )) || true
        continue
    fi

    if "$DRY_RUN"; then
        echo "reap.sh: DRY RUN — would destroy VM $VMID ($VM_NAME, $AGE_SOURCE, ${AGE_HOURS}h old)" >&2
        (( reaped++ )) || true
        continue
    fi

    echo "reap.sh: destroying VM $VMID ($VM_NAME, $AGE_SOURCE, ${AGE_HOURS}h old)" >&2

    # Stop first; ignore stop failure (VM may already be stopped or in error).
    vm_stop "$VMID" || true

    # Destroy. purge=1 removes disks and snapshots registered to this VM.
    if pvapi DELETE "/nodes/${PVE_NODE}/qemu/${VMID}?purge=1" >/dev/null; then
        if [ -f "$LEDGER_FILE" ]; then
            sed -i "/^${VMID} /d" "$LEDGER_FILE"
        fi
        # Remove the cloud-init snippet that holds the registration token.
        # An orphan by definition never had a teardown, so nothing removed it.
        _REAP_SNIPPET="${SNIPPETS_DIR}/gh-runner-${VMID}.yaml"
        if [ -f "$_REAP_SNIPPET" ]; then
            shred -u "$_REAP_SNIPPET" 2>/dev/null || rm -f "$_REAP_SNIPPET"
        fi
        echo "reap.sh: VM $VMID destroyed" >&2
        (( reaped++ )) || true
    else
        echo "reap.sh: VM $VMID: destroy failed" >&2
        (( skipped++ )) || true
    fi
done

if "$DRY_RUN"; then
    echo "reap.sh: DRY RUN complete — would destroy $reaped VM(s), skip $skipped" >&2
else
    echo "reap.sh: done — destroyed $reaped VM(s), kept $skipped" >&2
fi

# Exit non-zero when any VM was skipped for unknown age so the calling
# workflow surfaces the anomaly. Reaping something is not a success;
# failing to determine age and skipping is a warning that demands attention.
if [ "$unknown_age" -gt 0 ]; then
    echo "reap.sh: $unknown_age VM(s) had unknown age and were skipped — investigate" >&2
    exit 1
fi
