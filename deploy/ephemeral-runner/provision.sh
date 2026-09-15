#!/usr/bin/env bash
#
# Provision an ephemeral GitHub Actions runner on Proxmox via the HTTP API.
#
# Output contract (stdout):
#   Exactly one line of the form  vmid=<n>  is written to stdout immediately
#   after the clone and before any step that can fail post-clone. Callers MUST
#   capture stdout and parse the vmid= line BEFORE checking the exit status,
#   because a failure in a later step (agent delivery, start) still exits
#   non-zero while the VMID has already been emitted. A caller written as
#     VMID=$(ssh proxmox provision.sh ...)
#   loses the VMID on any non-zero exit. Use instead:
#     OUT=$(ssh proxmox provision.sh ...); rc=$?
#     VMID=$(printf '%s\n' "$OUT" | grep -oP 'vmid=\K[0-9]+')
#   Everything else (progress, errors) goes to stderr.
#
# Usage:
#   provision.sh <runner-label> <registration-token> <registration-url>
#
# <registration-url> must match the scope the token was minted for. An
# organization registration token requires the ORG url; passing the repository
# url with an org token fails at config.sh with a 404 that reads like a bad
# token. Registration is org-level so the PAT can hold only "Self-hosted
# runners" rather than repository Administration; the runner is confined to one
# repository by RUNNER_GROUP instead.
#
# The registration token is delivered by writing /run/gh-runner-init inside
# the guest via the qemu guest agent (POST .../agent/file-write). provision.sh
# never opens an SSH connection to the guest and writes no files to the
# hypervisor filesystem. The token must not appear in any curl process argv --
# visible to ps aux on the hypervisor -- so the content is written to a temp
# file and passed as --data-urlencode "content@FILE" rather than inline.
# The file lands root:root in the guest; the path unit must chown it before
# starting the runner service (see db-wd43).
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
#   TEMPLATE_VMID  -- source VM template id (default: 101)
#   CLONE_RETRIES  -- attempts before giving up on VMID collision (default: 5)
#   TASK_TIMEOUT   -- seconds to wait for a UPID task to complete (default: 120)
#   AGENT_TIMEOUT  -- seconds to wait for the guest agent to become ready (default: 120)
#   CRED_FILE      -- credential file to source (default: /etc/gh-ephemeral-runner/token)
#   PVE_API_HOST   -- Proxmox API hostname or IP (default: localhost)
#   PVE_API_PORT   -- Proxmox API port (default: 8006)
#   RUNNER_GROUP   -- runner group the guest registers into (default: ephemeral-ci)
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
CLONE_RETRIES="${CLONE_RETRIES:-5}"
TASK_TIMEOUT="${TASK_TIMEOUT:-120}"
AGENT_TIMEOUT="${AGENT_TIMEOUT:-120}"
CRED_FILE="${CRED_FILE:-/etc/gh-ephemeral-runner/token}"
# Where the Proxmox API lives. These default to loopback because that is right
# when the script runs on the hypervisor, but it no longer does: provision runs
# on a GitHub-hosted runner that reaches the host over the tailnet, and a
# hardcoded localhost made this script unable to provision anything from there
# at all (db-323).
PVE_API_HOST="${PVE_API_HOST:-localhost}"
PVE_API_PORT="${PVE_API_PORT:-8006}"
# The runner group the guest registers into. Org-level registration puts a
# runner in "Default" unless a group is named, and Default is visible to every
# repository in the organisation.
RUNNER_GROUP="${RUNNER_GROUP:-ephemeral-ci}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -ne 3 ]; then
    printf 'Usage: provision.sh <runner-label> <registration-token> <repo-url>\n' >&2
    exit 1
fi

LABEL="$1"
TOKEN="$2"
REPO_URL="$3"

# Validate label before any network step. Characters outside this set have no
# legitimate use in a runner label.
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
        "https://${PVE_API_HOST}:${PVE_API_PORT}/api2/json${path}" "$@")" || {
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
            "https://${PVE_API_HOST}:${PVE_API_PORT}/api2/json/nodes/${PVE_NODE}/qemu/${vmid}/config")" || {
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
# server; do not proceed to start the VM.
poll_task "$clone_upid" || exit 1

# Emit the VMID now -- before any step that can fail -- so callers can tear
# down even if we die later. See the output contract at the top.
#
# There is deliberately no ledger write here. A file on this machine's disk
# cannot be read by teardown.sh, which runs in a different job on a different
# ephemeral runner. Ownership is established from the hypervisor instead: the
# VM's name, its pool membership, and its template flag.
printf 'vmid=%s\n' "$VMID"

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

# --- Wait for guest agent ---
#
# The guest agent needs time to start after the VM boots. Poll /agent/ping
# until it responds before attempting file-write, which would fail immediately
# if the agent is not yet running.
printf 'provision.sh: waiting for guest agent on VM %s (timeout %ss)\n' "$VMID" "$AGENT_TIMEOUT" >&2
agent_deadline=$(( $(date +%s) + AGENT_TIMEOUT ))
while true; do
    # The inline pvapi() returns non-0 on non-2xx. If pvapi.sh is ever
    # sourced here instead, pvapi() returns 0 even on 500 but sets
    # PVAPI_STATUS. The PVAPI_STATUS:-200 default makes both work: the
    # inline version leaves PVAPI_STATUS unset, so it defaults to 200 on
    # any successful return (which the inline version only does on 2xx).
    _ping_ok=0
    if pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/agent/ping" >/dev/null 2>&1; then
        case "${PVAPI_STATUS:-200}" in 2??) _ping_ok=1 ;; esac
    fi
    [ "$_ping_ok" -eq 1 ] && break
    if [ "$(date +%s)" -ge "$agent_deadline" ]; then
        printf 'provision.sh: timed out waiting for guest agent on VM %s (%ss)\n' \
            "$VMID" "$AGENT_TIMEOUT" >&2
        exit 1
    fi
    sleep 2
done

# --- Deliver the guest script, then the token ---
#
# ORDER IS LOAD-BEARING. The guest's ephemeral-runner.path unit watches
# /run/gh-runner-init and starts the service the moment that file appears, so
# start-runner.sh must already be in place. Writing the script first and the
# token second is what makes that safe.
#
# The script is shipped from this repository on every run rather than baked
# into the VM template. That keeps it version-controlled and reviewable, and
# means changing it never requires cloning, editing and resealing the template.
printf 'provision.sh: delivering guest script to VM %s\n' "$VMID" >&2
pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/agent/file-write" \
    --data-urlencode "file=/home/runner/start-runner.sh" \
    --data-urlencode "content@${SCRIPT_DIR}/guest/start-runner.sh" || exit 1

# file-write lands the file root:root and non-executable. The service runs as
# User=runner and execs this path, so both have to be corrected before the
# token arrives and the path unit fires.
pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/agent/exec" \
    --data-urlencode "command=/bin/chown" \
    --data-urlencode "command=runner:runner" \
    --data-urlencode "command=/home/runner/start-runner.sh" || exit 1
pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/agent/exec" \
    --data-urlencode "command=/bin/chmod" \
    --data-urlencode "command=0755" \
    --data-urlencode "command=/home/runner/start-runner.sh" || exit 1

# Write the token content to a temp file so it never appears in any curl
# process argv (visible to ps aux). The file lands root:root in the guest; the
# path unit chowns it before starting the runner service.
printf 'provision.sh: delivering token to VM %s via guest agent\n' "$VMID" >&2
_token_file="$(mktemp)"
printf 'RUNNER_LABEL=%s\nRUNNER_TOKEN=%s\nRUNNER_URL=%s\nRUNNER_GROUP=%s\n' \
    "$LABEL" "$TOKEN" "$REPO_URL" "$RUNNER_GROUP" > "$_token_file"
pvapi POST "/nodes/${PVE_NODE}/qemu/${VMID}/agent/file-write" \
    --data-urlencode "file=/run/gh-runner-init" \
    --data-urlencode "content@${_token_file}" || { rm -f "$_token_file"; exit 1; }
rm -f "$_token_file"

printf 'provision.sh: VM %s started; runner credentials delivered via guest agent\n' "$VMID" >&2
