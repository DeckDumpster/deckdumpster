#!/usr/bin/env bash
#
# Provision an ephemeral GitHub Actions runner on Proxmox.
# Prints the VMID on stdout; everything else goes to stderr.
#
# Usage:
#   provision.sh <runner-label> <registration-token> <repo-url>
#
# Registration is done over SSH rather than `qm guest exec`, with the token
# piped via stdin rather than placed on the command line. `qm guest exec` logs
# every argv word to the Proxmox task journal; a token on stdin is visible to
# neither — and a registration token in a system journal is effectively
# unrevocable for its lifetime (~1 h).
#
# Environment variables:
#   TEMPLATE_VMID   — source VM template id (default: 101)
#   RUNNER_SSH_KEY  — path to SSH private key for the runner guest
#                     (default: ~/.ssh/gh-runner)
#   RUNNER_SSH_USER — SSH user in the guest (default: runner)
#   LEDGER_FILE     — active-runner ledger path
#                     (default: /var/lib/gh-ephemeral-runner/active)
#   CLONE_RETRIES   — attempts before giving up on VMID collision (default: 5)
#
set -euo pipefail

TEMPLATE_VMID="${TEMPLATE_VMID:-101}"
RUNNER_SSH_KEY="${RUNNER_SSH_KEY:-$HOME/.ssh/gh-runner}"
RUNNER_SSH_USER="${RUNNER_SSH_USER:-runner}"
LEDGER_FILE="${LEDGER_FILE:-/var/lib/gh-ephemeral-runner/active}"
CLONE_RETRIES="${CLONE_RETRIES:-5}"

if [ $# -ne 3 ]; then
    echo "Usage: provision.sh <runner-label> <registration-token> <repo-url>" >&2
    exit 1
fi

LABEL="$1"
TOKEN="$2"
REPO_URL="$3"

# Ensure the ledger directory exists before we try to write to it.
mkdir -p "$(dirname "$LEDGER_FILE")"

# --- Pick a VMID ---
#
# qm nextid is the tool's own answer to "what id is free right now". RANDOM
# collides: two concurrent provisions both draw from the same 8000-id space
# and may land on the same number, which surfaces as qm clone failing with an
# opaque error on a random CI run — the kind of intermittent red that costs
# more to diagnose than it ever cost to avoid.
#
# qm nextid itself races against a concurrent provision, so re-check the
# chosen id is still free before cloning and retry on collision.
pick_vmid() {
    local i vmid
    for i in $(seq 1 "$CLONE_RETRIES"); do
        vmid="$(qm nextid)"
        # A second call to qm nextid on the same host may return the same id
        # until the first clone commits; verify it is unclaimed.
        if ! qm config "$vmid" >/dev/null 2>&1; then
            echo "$vmid"
            return 0
        fi
        echo "provision.sh: VMID $vmid already in use, retrying ($i/$CLONE_RETRIES)" >&2
        sleep 1
    done
    echo "provision.sh: could not obtain a free VMID after $CLONE_RETRIES attempts" >&2
    return 1
}

VMID="$(pick_vmid)"

# --- Clone ---
#
# Print the VMID to stdout and write it to the ledger immediately after the
# clone, before starting the VM. If this script dies between clone and the
# caller capturing its output, the ledger still records the VM so reap.sh
# can find and destroy it.
echo "provision.sh: cloning template $TEMPLATE_VMID → VMID $VMID" >&2
qm clone "$TEMPLATE_VMID" "$VMID" --name "gh-runner-${VMID}" --full 0 >&2

# Ledger entry: VMID, label, epoch — one record per line, space-separated.
printf '%s %s %s\n' "$VMID" "$LABEL" "$(date +%s)" >>"$LEDGER_FILE"

# Now that the ledger is written, tell the caller the VMID. From this point on
# the caller can run teardown.sh to clean up even if we die.
echo "$VMID"

# --- Start ---
echo "provision.sh: starting VM $VMID" >&2
qm start "$VMID" >&2

# --- Wait for guest agent ---
#
# qm guest cmd ping is the first real readiness signal. A fixed sleep races
# against VM boot time and underestimates on a loaded host; a timeout loop
# against the agent's actual answer does not.
AGENT_TIMEOUT="${AGENT_TIMEOUT:-120}"
echo "provision.sh: waiting for guest agent on VM $VMID (timeout ${AGENT_TIMEOUT}s)" >&2
deadline=$(( $(date +%s) + AGENT_TIMEOUT ))
while true; do
    if qm guest cmd "$VMID" ping >/dev/null 2>&1; then
        echo "provision.sh: guest agent answered" >&2
        break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "provision.sh: timed out waiting for guest agent on VM $VMID" >&2
        exit 1
    fi
    sleep 2
done

# --- Discover guest IP ---
#
# Ask the guest agent for the VM's IP rather than assuming a static address.
# Filter to the first non-loopback IPv4 address reported.
GUEST_IP="$(
    qm guest cmd "$VMID" network-get-interfaces 2>/dev/null \
    | python3 -c "
import json, sys
for iface in json.load(sys.stdin).get('result', []):
    if iface.get('name') == 'lo':
        continue
    for addr in iface.get('ip-addresses', []):
        if addr.get('ip-address-type') == 'ipv4':
            print(addr['ip-address'])
            sys.exit(0)
sys.exit(1)
"
)"
if [ -z "$GUEST_IP" ]; then
    echo "provision.sh: could not determine guest IP for VM $VMID" >&2
    exit 1
fi
echo "provision.sh: guest IP is $GUEST_IP" >&2

# --- Register the runner ---
#
# Registration pipes the token to the remote script via stdin rather than
# placing it on the command line. A token on the command line is briefly
# visible in `ps aux` output on the host; a token on stdin is not. The remote
# script /usr/local/bin/register-runner reads the label as its first argument
# and the token + repo URL from stdin (one per line, token first). This is why
# SSH is used instead of `qm guest exec` — qm logs every argv word to the
# Proxmox task journal; SSH does not log stdin.
#
# set -x is deliberately NOT active here. The printf lines that write the
# token are not printed; the SSH invocation itself is not echoed.
echo "provision.sh: registering runner on VM $VMID (label: $LABEL)" >&2
{
    printf '%s\n' "$TOKEN"
    printf '%s\n' "$REPO_URL"
} | ssh -i "$RUNNER_SSH_KEY" \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=30 \
        -o BatchMode=yes \
        "${RUNNER_SSH_USER}@${GUEST_IP}" \
        "/usr/local/bin/register-runner $(printf '%s' "$LABEL")" >&2

echo "provision.sh: VM $VMID is ready" >&2
