#!/usr/bin/env bash
#
# Destroy an ephemeral GitHub Actions runner VM on Proxmox.
# Exits zero if the VM is already gone — teardown runs under if: always()
# and must be idempotent, or every cancelled run reports a spurious failure.
#
# Usage:
#   teardown.sh <vmid>
#
# Three guards prevent destroying the wrong thing:
#   1. Empty or non-numeric argument → exit non-zero, qm is never called.
#      A provision job that dies before emitting its output leaves the
#      caller's vmid variable empty; without this guard the teardown step
#      runs qm destroy with no id.
#   2. VMID not in the ledger → exit non-zero. A VMID that was never
#      recorded by provision.sh does not belong to this runner pool.
#   3. VM name does not match gh-runner-<vmid> → exit non-zero. A clone
#      that failed and left the id pointing at an unrelated VM must not
#      be purged. Name is read with `qm config`, not by parsing qm list
#      output positionally, which is fragile.
#   4. VMID equals TEMPLATE_VMID → exit non-zero, unconditionally.
#
# Environment variables:
#   TEMPLATE_VMID — source VM template id (default: 101)
#   LEDGER_FILE   — active-runner ledger path
#                   (default: /var/lib/gh-ephemeral-runner/active)
#
set -euo pipefail

TEMPLATE_VMID="${TEMPLATE_VMID:-101}"
LEDGER_FILE="${LEDGER_FILE:-/var/lib/gh-ephemeral-runner/active}"

if [ $# -ne 1 ]; then
    echo "Usage: teardown.sh <vmid>" >&2
    exit 1
fi

VMID="$1"

# Guard 1: argument must be a non-empty integer.
if [ -z "$VMID" ] || ! [[ "$VMID" =~ ^[0-9]+$ ]]; then
    echo "teardown.sh: refusing empty or non-numeric VMID: '$VMID'" >&2
    exit 1
fi

# Guard 4: refuse the template itself, even if it somehow appears in the ledger.
if [ "$VMID" -eq "$TEMPLATE_VMID" ]; then
    echo "teardown.sh: refusing to destroy template VMID $TEMPLATE_VMID" >&2
    exit 1
fi

# Guard 2: VMID must be in the ledger.
if [ ! -f "$LEDGER_FILE" ] || ! grep -qP "^${VMID} " "$LEDGER_FILE"; then
    echo "teardown.sh: VMID $VMID not found in ledger $LEDGER_FILE — refusing" >&2
    exit 1
fi

# Guard 3: verify the VM's name matches what provision.sh set.
EXPECTED_NAME="gh-runner-${VMID}"
if ! qm config "$VMID" >/dev/null 2>&1; then
    # VM does not exist — already gone. Idempotent exit.
    echo "teardown.sh: VM $VMID not found on host — already gone" >&2
    # Still drop the ledger line so the ledger stays accurate.
    if [ -f "$LEDGER_FILE" ]; then
        sed -i "/^${VMID} /d" "$LEDGER_FILE"
    fi
    exit 0
fi

ACTUAL_NAME="$(qm config "$VMID" | awk -F': ' '/^name:/{print $2}')"
if [ "$ACTUAL_NAME" != "$EXPECTED_NAME" ]; then
    echo "teardown.sh: VM $VMID name is '$ACTUAL_NAME', expected '$EXPECTED_NAME' — refusing" >&2
    exit 1
fi

# --- Destroy ---
echo "teardown.sh: stopping VM $VMID" >&2
qm stop "$VMID" --timeout 30 >&2 || true

echo "teardown.sh: destroying VM $VMID" >&2
qm destroy "$VMID" --purge >&2

# Drop the ledger line.
if [ -f "$LEDGER_FILE" ]; then
    sed -i "/^${VMID} /d" "$LEDGER_FILE"
fi

echo "teardown.sh: VM $VMID destroyed and removed from ledger" >&2
