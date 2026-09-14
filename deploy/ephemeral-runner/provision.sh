#!/usr/bin/env bash
#
# Provision an ephemeral GitHub Actions runner on Proxmox.
#
# Output contract (stdout):
#   Exactly one line of the form  vmid=<n>  is written to stdout immediately
#   after the ledger entry, before any step that can fail. Callers MUST capture
#   stdout and parse the vmid= line BEFORE checking the exit status, because a
#   failure in a later step (agent timeout, IP discovery, registration) still
#   exits non-zero while the VMID has already been emitted. A caller written as
#     VMID=$(ssh proxmox provision.sh ...)
#   loses the VMID on any non-zero exit. Use instead:
#     OUT=$(ssh proxmox provision.sh ...) ; rc=$? ; VMID=$(grep -oP 'vmid=\K\d+' <<< "$OUT")
#   Everything else (progress, errors) goes to stderr.
#
# Usage:
#   provision.sh <runner-label> <registration-token> <repo-url>
#
# Registration is done over SSH rather than `qm guest exec`, with the token,
# repo URL, and runner label all piped via stdin rather than placed on the
# command line. `qm guest exec` logs every argv word to the Proxmox task
# journal; a token on stdin is visible to neither — and a registration token
# in a system journal is effectively unrevocable for its lifetime (~1 h).
# The label is kept off argv for the same reason: it is the one field that
# flows from workflow YAML through the hypervisor into a remote shell, and
# leaving it on argv means a label with special characters runs code there.
#
# The remote script /usr/local/bin/register-runner reads from stdin:
#   line 1: token
#   line 2: repo URL
#   line 3: runner label
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

# Validate the label before any network step. The label flows from workflow
# YAML into a remote shell (stdin pipe, but validated here as defence in depth);
# characters outside this set have no legitimate use in a runner label and
# would be injection candidates if the delivery mechanism ever changes.
if ! printf '%s' "$LABEL" | grep -qE '^[A-Za-z0-9._-]+$'; then
    echo "provision.sh: label '$LABEL' contains invalid characters (allowed: A-Za-z0-9._-)" >&2
    exit 1
fi

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
# Write the VMID to stdout and to the ledger immediately after the clone,
# before starting the VM. See the output contract in the header: a caller
# that wraps this in $() loses the VMID on any later failure. The ledger
# records the VM so reap.sh can find and destroy it even if the caller
# never captured the vmid= line.
echo "provision.sh: cloning template $TEMPLATE_VMID → VMID $VMID" >&2
qm clone "$TEMPLATE_VMID" "$VMID" --name "gh-runner-${VMID}" --full 0 >&2

# Ledger entry: VMID, label, epoch — one record per line, space-separated.
printf '%s %s %s\n' "$VMID" "$LABEL" "$(date +%s)" >>"$LEDGER_FILE"

# Emit the VMID now — before any step that can fail — so callers can tear
# down even if we die later. See output contract in the header.
echo "vmid=$VMID"

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
# Ask the guest agent for the VM's network interfaces and select the one
# routable from the hypervisor. Two exclusions apply:
#
# 1. Interface name: skip loopback (lo) and container bridge patterns
#    (podman0, cni-podman0, docker0, veth*, br-*). The template requires
#    Podman; a host with container networking reports bridge interfaces with
#    ordinary IPv4 addresses, and the guest agent does not promise an
#    ordering — so the first non-lo address can be a bridge address that is
#    unreachable from the hypervisor.
#
# 2. Address subnet: skip 10.88.0.0/16 (Podman CNI default) and
#    172.16.0.0/12 (Docker's range). Interface name filtering handles the
#    common case; subnet filtering is a second bound for bridge names we
#    did not anticipate.
#
# Fail loudly when more than one candidate survives: a silent pick would
# reproduce the original bug on any network layout we did not plan for.
GUEST_IP="$(
    qm guest cmd "$VMID" network-get-interfaces 2>/dev/null \
    | python3 -c "
import json, sys, re

BRIDGE_PATTERN = re.compile(r'^(lo|podman\d*|cni-podman\d*|docker\d*|veth|br-)')

def in_container_net(ip):
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        n = (int(parts[0]) << 24 | int(parts[1]) << 16 |
             int(parts[2]) <<  8 | int(parts[3]))
    except ValueError:
        return False
    # 10.88.0.0/16 — Podman CNI default
    if (n & 0xFFFF0000) == 0x0A580000:
        return True
    # 172.16.0.0/12 — Docker / RFC 1918 container range
    if (n & 0xFFF00000) == 0xAC100000:
        return True
    return False

candidates = []
for iface in json.load(sys.stdin).get('result', []):
    if BRIDGE_PATTERN.match(iface.get('name', '')):
        continue
    for addr in iface.get('ip-addresses', []):
        if addr.get('ip-address-type') == 'ipv4':
            ip = addr['ip-address']
            if not in_container_net(ip):
                candidates.append(ip)

if len(candidates) == 0:
    print('provision.sh: no routable guest IPv4 found', file=sys.stderr)
    sys.exit(1)
if len(candidates) > 1:
    print(
        'provision.sh: ambiguous guest IP — ' + str(candidates) +
        '; check container networking or set a static guest IP',
        file=sys.stderr,
    )
    sys.exit(1)
print(candidates[0])
"
)"
if [ -z "$GUEST_IP" ]; then
    echo "provision.sh: could not determine guest IP for VM $VMID" >&2
    exit 1
fi
echo "provision.sh: guest IP is $GUEST_IP" >&2

# --- Register the runner ---
#
# Registration pipes the token, repo URL, and runner label to the remote
# script via stdin rather than placing them on the command line. Values on
# the command line are briefly visible in `ps aux` on the host and logged
# word-by-word by `qm guest exec`; values on stdin are not. This is why
# SSH is used instead of `qm guest exec`.
#
# SSH options:
#   UserKnownHostsFile=/dev/null — every ephemeral VM is a fresh clone with
#     a fresh host key, and DHCP reuses addresses across runs. Without this,
#     StrictHostKeyChecking=no still refuses when known_hosts holds a
#     *different* key for the same address — which is guaranteed once the
#     DHCP pool wraps. /dev/null also prevents stale entries from accumulating
#     in the Proxmox host's known_hosts across every CI run.
#   StrictHostKeyChecking=no — we cloned this VM ourselves moments ago on a
#     host we are already root on, and it is reachable only over the private
#     Proxmox bridge. Trust-on-first-use is appropriate here; do not revert
#     to the default without also solving host-key distribution.
#   LogLevel=ERROR — suppresses the "Warning: Permanently added ..." line
#     that StrictHostKeyChecking=no emits to stderr, which would otherwise
#     appear in provision.sh's own stderr output.
#
# set -x is deliberately NOT active here. The printf lines that write the
# token are not printed; the SSH invocation itself is not echoed.
echo "provision.sh: registering runner on VM $VMID (label: $LABEL)" >&2
{
    printf '%s\n' "$TOKEN"
    printf '%s\n' "$REPO_URL"
    printf '%s\n' "$LABEL"
} | ssh -i "$RUNNER_SSH_KEY" \
        -o UserKnownHostsFile=/dev/null \
        -o StrictHostKeyChecking=no \
        -o LogLevel=ERROR \
        -o ConnectTimeout=30 \
        -o BatchMode=yes \
        "${RUNNER_SSH_USER}@${GUEST_IP}" \
        /usr/local/bin/register-runner >&2

echo "provision.sh: VM $VMID is ready" >&2
