#!/usr/bin/env bash
#
# Provision an ephemeral GitHub Actions runner on Proxmox via the HTTP API.
#
# Output contract (stdout):
#   Exactly one line of the form  vmid=<n>  is written to stdout after the
#   ledger entry and before any step that can fail post-clone. Callers MUST
#   capture stdout and parse the vmid= line BEFORE checking the exit status,
#   because a failure in a later step (config injection, start) still exits
#   non-zero while the VMID has already been emitted. A caller written as
#     VMID=$(ssh proxmox provision.sh ...)
#   loses the VMID on any non-zero exit. Use instead:
#     OUT=$(ssh proxmox provision.sh ...); rc=$?
#     VMID=$(printf '%s\n' "$OUT" | grep -oP 'vmid=\K[0-9]+')
#   Everything else (progress, errors) goes to stderr.
#
# Usage:
#   provision.sh <runner-label> <registration-token> <repo-url>
#
# The registration token is injected as cloud-init data at clone time; the
# guest registers itself from that data. provision.sh never opens an SSH
# connection to the guest. The token must not appear in the VM's description,
# its name, or anywhere GET .../config returns to a lower-privileged reader --
# it lives only in the cloud-init snippet file at
# $SNIPPETS_DIR/gh-runner-<vmid>.yaml. teardown.sh is responsible for
# deleting that file.
#
# Proxmox credentials (from $CRED_FILE, mode 0600, owned by gh-runner):
#   PVE_TOKEN_ID     -- Proxmox API token id (user@realm!tokenname)
#   PVE_TOKEN_SECRET -- Proxmox API token secret
#   PVE_NODE         -- Proxmox node name
#
# These three are never accepted as command-line arguments -- an unset variable
# and a dead API produce identical symptoms at the curl layer, and naming the
# missing one at startup is the only way to distinguish them.
#
# Environment variables:
#   TEMPLATE_VMID -- source VM template id (default: 101)
#   LEDGER_FILE   -- active-runner ledger (default: /var/lib/gh-ephemeral-runner/active)
#   CLONE_RETRIES -- attempts before giving up on VMID collision (default: 5)
#   SNIPPETS_DIR  -- Proxmox local snippets storage (default: /var/lib/vz/snippets)
#   TASK_TIMEOUT  -- seconds to wait for a UPID task to complete (default: 120)
#   CRED_FILE     -- credential file to source (default: /etc/gh-ephemeral-runner/token)
#
# API transport notes:
#   -k: loopback only. The request never leaves the host, so anyone positioned
#       to intercept it already has local access. Do not copy this flag to a
#       call that goes over the network.
#   -sS: -s suppresses the progress meter; -S restores curl's transport-error
#       messages to stderr. Never use -s alone -- connection refused, TLS
#       failure, and a malformed URL from an unset variable all produce empty
#       output and HTTP 000 with no indication of cause.
#   Never -f/--fail: it discards the response body on HTTP >=400. The Proxmox
#       API returns its error reason in that body; discarding it makes every
#       auth and validation failure arrive as a bare exit code with nothing to
#       act on.
#
set -euo pipefail

TEMPLATE_VMID="${TEMPLATE_VMID:-101}"
LEDGER_FILE="${LEDGER_FILE:-/var/lib/gh-ephemeral-runner/active}"
CLONE_RETRIES="${CLONE_RETRIES:-5}"
SNIPPETS_DIR="${SNIPPETS_DIR:-/var/lib/vz/snippets}"
TASK_TIMEOUT="${TASK_TIMEOUT:-120}"
CRED_FILE="${CRED_FILE:-/etc/gh-ephemeral-runner/token}"

if [ $# -ne 3 ]; then
    printf 'Usage: provision.sh <runner-label> <registration-token> <repo-url>\n' >&2
    exit 1
fi

LABEL="$1"
TOKEN="$2"
REPO_URL="$3"

# Validate label before any network step. The label flows into cloud-init
# user-data; characters outside this set have no legitimate use in a runner
# label.
if ! printf '%s' "$LABEL" | grep -qE '^[A-Za-z0-9._-]+$'; then
    printf 'provision.sh: label contains invalid characters (allowed: A-Za-z0-9._-)\n' >&2
    exit 1
fi

# Source credentials. Fail fast with a named cause before calling curl --
# an unset variable and a dead API look the same at the curl layer.
if [ -f "$CRED_FILE" ]; then
    # shellcheck source=/dev/null
    . "$CRED_FILE"
fi
: "${PVE_TOKEN_ID:?credential not set -- is $CRED_FILE sourced and readable?}"
: "${PVE_TOKEN_SECRET:?credential not set -- is $CRED_FILE sourced and readable?}"
: "${PVE_NODE:?credential not set -- is $CRED_FILE sourced and readable?}"

mkdir -p "$(dirname "$LEDGER_FILE")"

# ---------------------------------------------------------------------------
# pvapi <METHOD> <path> [curl-args...]
#
# Calls the Proxmox REST API. Writes the response body to stdout. Returns 0
# on 2xx, 1 on any HTTP error or curl transport failure. On non-2xx, logs
# METHOD, path, and the HTTP status to stderr; the body (which contains the
# API's reason) is still emitted so the caller can log it.
#
# -o to a temp file separates body from the -w status code, so the body
# always reaches stdout regardless of HTTP status.
# ---------------------------------------------------------------------------
pvapi() {
    local method="$1" path="$2"; shift 2
    local body_file code
    body_file="$(mktemp)"
    code="$(curl -sS -k -o "$body_file" -w '%{http_code}' -X "$method" \
        -H "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" \
        "https://localhost:8006/api2/json${path}" "$@")" || {
        rm -f "$body_file"
        printf 'provision.sh: curl transport error (%s %s)\n' "$method" "$path" >&2
        return 1
    }
    cat "$body_file"
    rm -f "$body_file"
    case "$code" in 2??) return 0 ;; esac
    printf 'provision.sh: pvapi %s %s -> HTTP %s\n' "$method" "$path" "$code" >&2
    return 1
}

# ---------------------------------------------------------------------------
# poll_task <upid>
#
# Waits for a Proxmox async task to reach status=stopped. Returns 0 when
# exitstatus=OK, 1 when exitstatus is anything else or when TASK_TIMEOUT
# expires. Every POST to a Proxmox action endpoint returns a UPID immediately
# and the work happens afterwards -- a script that fires the clone and proceeds
# straight to config injection races intermittently. That is the defect class
# this bead exists to remove.
# ---------------------------------------------------------------------------
poll_task() {
    local upid="$1"
    local encoded deadline body status exitstatus
    encoded="$(printf '%s' "$upid" | python3 -c \
        'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip(),safe=""))')"
    deadline=$(( $(date +%s) + TASK_TIMEOUT ))
    while true; do
        body="$(pvapi GET "/nodes/${PVE_NODE}/tasks/${encoded}/status")" || return 1
        status="$(printf '%s\n' "$body" | python3 -c \
            'import json,sys; print(json.load(sys.stdin).get("data",{}).get("status",""))')"
        if [ "$status" = "stopped" ]; then
            exitstatus="$(printf '%s\n' "$body" | python3 -c \
                'import json,sys; print(json.load(sys.stdin).get("data",{}).get("exitstatus",""))')"
            if [ "$exitstatus" = "OK" ]; then
                return 0
            fi
            printf 'provision.sh: task %s failed (exitstatus=%s)\n' "$upid" "$exitstatus" >&2
            return 1
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            printf 'provision.sh: timed out waiting for task %s (%ss)\n' "$upid" "$TASK_TIMEOUT" >&2
            return 1
        fi
        sleep 2
    done
}

# ---------------------------------------------------------------------------
# pick_vmid
#
# GET /cluster/nextid, then verify the returned id is unclaimed (GET config
# returns 404). Retry on collision -- nextid races against concurrent provisions.
# 404 from GET .../config is the success case; 2xx means in use.
# ---------------------------------------------------------------------------
pick_vmid() {
    local i vmid body config_code
    for i in $(seq 1 "$CLONE_RETRIES"); do
        body="$(pvapi GET "/cluster/nextid")" || return 1
        vmid="$(printf '%s\n' "$body" | python3 -c \
            'import json,sys; print(json.load(sys.stdin).get("data",""))')"
        if [ -z "$vmid" ]; then
            printf 'provision.sh: /cluster/nextid returned empty data\n' >&2
            return 1
        fi
        config_code="$(curl -sS -k -o /dev/null -w '%{http_code}' -X GET \
            -H "Authorization: PVEAPIToken=${PVE_TOKEN_ID}=${PVE_TOKEN_SECRET}" \
            "https://localhost:8006/api2/json/nodes/${PVE_NODE}/qemu/${vmid}/config")" || {
            printf 'provision.sh: curl transport error checking VMID %s\n' "$vmid" >&2
            return 1
        }
        case "$config_code" in
            404)
                printf '%s' "$vmid"
                return 0
                ;;
            2??)
                printf 'provision.sh: VMID %s in use, retrying (%s/%s)\n' \
                    "$vmid" "$i" "$CLONE_RETRIES" >&2
                sleep 1
                ;;
            *)
                printf 'provision.sh: unexpected HTTP %s checking VMID %s\n' \
                    "$config_code" "$vmid" >&2
                return 1
                ;;
        esac
    done
    printf 'provision.sh: could not obtain a free VMID after %s attempts\n' "$CLONE_RETRIES" >&2
    return 1
}

# --- Pick a VMID ---
VMID="$(pick_vmid)" || exit 1

# --- Clone ---
#
# pool=ephemeral-ci is required. A pool-scoped grant cannot allocate outside
# its pool, so omitting it causes the clone to fail with a permissions error
# even if the token has VM.Clone on the template.
printf 'provision.sh: cloning template %s -> VMID %s\n' "$TEMPLATE_VMID" "$VMID" >&2
clone_body="$(pvapi POST "/nodes/${PVE_NODE}/qemu/${TEMPLATE_VMID}/clone" \
    --data-urlencode "newid=${VMID}" \
    --data-urlencode "name=gh-runner-${VMID}" \
    --data-urlencode "full=0" \
    --data-urlencode "pool=ephemeral-ci")" || exit 1
clone_upid="$(printf '%s\n' "$clone_body" | python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("data",""))')"
if [ -z "$clone_upid" ]; then
    printf 'provision.sh: clone POST returned no UPID\n' >&2
    exit 1
fi

# Poll the clone task. A non-OK exitstatus means the clone failed on the
# server; do not proceed to inject cloud-init or start the VM.
poll_task "$clone_upid" || exit 1

# Write the ledger entry and emit the VMID now -- before any step that can
# fail -- so callers can tear down even if we die later. See output contract.
printf '%s %s %s\n' "$VMID" "$LABEL" "$(date +%s)" >>"$LEDGER_FILE"
printf 'vmid=%s\n' "$VMID"

# --- Inject cloud-init user-data ---
#
# Write runner credentials to a snippet file and set cicustom on the VM
# config. The token travels as cloud-init data and is never in the VM's
# description, name, or any config field visible to a lower-privileged reader.
# teardown.sh deletes $SNIPPETS_DIR/gh-runner-<vmid>.yaml on VM destruction.
printf 'provision.sh: injecting cloud-init data for VM %s\n' "$VMID" >&2
SNIPPET_PATH="${SNIPPETS_DIR}/gh-runner-${VMID}.yaml"
mkdir -p "$SNIPPETS_DIR"
cat >"$SNIPPET_PATH" <<USERDATA
#cloud-config
write_files:
  - path: /run/gh-runner-init
    permissions: '0600'
    owner: 'runner:runner'
    content: |
      RUNNER_LABEL=${LABEL}
      RUNNER_TOKEN=${TOKEN}
      RUNNER_REPO_URL=${REPO_URL}
USERDATA

config_body="$(pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/config" \
    --data-urlencode "cicustom=user=local:snippets/gh-runner-${VMID}.yaml")" || exit 1
config_upid="$(printf '%s\n' "$config_body" | python3 -c \
    'import json,sys; d=json.load(sys.stdin).get("data"); print(d if d else "")')"
if [ -n "$config_upid" ]; then
    poll_task "$config_upid" || exit 1
fi

# --- Start ---
printf 'provision.sh: starting VM %s\n' "$VMID" >&2
start_body="$(pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/status/start")" || exit 1
start_upid="$(printf '%s\n' "$start_body" | python3 -c \
    'import json,sys; print(json.load(sys.stdin).get("data",""))')"
if [ -z "$start_upid" ]; then
    printf 'provision.sh: start POST returned no UPID\n' >&2
    exit 1
fi
poll_task "$start_upid" || exit 1

printf 'provision.sh: VM %s started; runner will self-register via cloud-init\n' "$VMID" >&2
