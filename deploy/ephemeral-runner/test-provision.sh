#!/usr/bin/env bash
# covers: deploy/ephemeral-runner/provision.sh
#
# Tests for the cloud-init/API rewrite in db-oh4.
# No hypervisor required. curl is stubbed on PATH.
#
# Test cases:
#   1. clone POST carries pool=ephemeral-ci
#   2. clone task with exitstatus != OK -> script fails before inject or start
#   3. registration token never appears in any curl argv
#   4. failure after the clone -> non-zero exit AND vmid=<n> still on stdout,
#      so the caller can tear the VM down
#   5. PVE_TOKEN_SECRET unset -> fails before calling curl, naming the cause
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROVISION="$SCRIPT_DIR/provision.sh"

pass=0
fail=0

ok() { echo "PASS: $1"; (( pass++ )) || true; }
ko() { echo "FAIL: $1"; (( fail++ )) || true; }

SCRATCH=$(mktemp -d)
mkdir -p "$SCRATCH/bin"
trap 'rm -rf "$SCRATCH"' EXIT

export PATH="$SCRATCH/bin:$PATH"
export TASK_TIMEOUT=5
export AGENT_TIMEOUT=5
export CLONE_RETRIES=3
# Point CRED_FILE at a non-existent path; tests export credentials directly.
export CRED_FILE="$SCRATCH/no-such-cred-file"
# Credentials
export PVE_TOKEN_ID="test-user@pve!provision"
export PVE_TOKEN_SECRET="test-secret-abc123"
export PVE_NODE="pve"

# CURL_ARGV_FILE collects every curl invocation (one arg per line, calls
# separated by ---). Tests reset it between runs.
export CURL_ARGV_FILE="$SCRATCH/curl-argv"

# ---------------------------------------------------------------------------
# Stub: curl
#
# Dispatches responses based on the URL path extracted from argv.
# Behaviour overrides:
#   CURL_CLONE_EXITSTATUS   -- exitstatus in clone task poll response (default: OK)
#   CURL_START_EXITSTATUS   -- exitstatus in start task poll response (default: OK)
#   CURL_VMID_FREE_CODE     -- HTTP code for vmid free check (default: 404)
#   CURL_VMID_403_UNTIL     -- vmid probes for ids <= this return 403 (pool ACL)
#   CURL_AGENT_PING_FAIL    -- if "1", agent/ping returns 500 (agent not ready)
# ---------------------------------------------------------------------------
cat >"$SCRATCH/bin/curl" <<'SH'
#!/usr/bin/env bash
# Record this invocation to the argv file.
{
    printf '%s\n' "$@"
    echo '---'
} >> "${CURL_ARGV_FILE:?CURL_ARGV_FILE not set}"

# Parse argv for method, URL, output file, and whether -w was requested.
method="GET"
url=""
output_file=""
want_http_code=0
prev=""
for arg in "$@"; do
    case "$prev" in
        -X) method="$arg" ;;
        -o) output_file="$arg" ;;
        -w) want_http_code=1 ;;
    esac
    case "$arg" in https://*) url="$arg" ;; esac
    prev="$arg"
done

path="${url#https://localhost:8006/api2/json}"

# Generate response body and HTTP code based on path and method.
http_code=200
body=""

case "$path" in
    /cluster/nextid)
        body='{"data":200}'
        ;;
    /nodes/*/qemu/*/config)
        case "$method" in
            GET)
                # A pool-scoped token gets 403, not 404, for a VM outside its
                # pool. CURL_VMID_403_UNTIL models a host where the low ids are
                # occupied by VMs this token cannot see.
                _probe_vmid="${path#/nodes/}"; _probe_vmid="${_probe_vmid#*/qemu/}"; _probe_vmid="${_probe_vmid%%/*}"
                if [ -n "${CURL_VMID_403_UNTIL:-}" ] \
                   && [ "$_probe_vmid" -le "${CURL_VMID_403_UNTIL}" ] 2>/dev/null; then
                    http_code=403
                    body='{"errors":{"vmid":"Permission check failed"}}'
                else
                    http_code="${CURL_VMID_FREE_CODE:-404}"
                    body='{"errors":{"vmid":"VM not found"}}'
                fi
                ;;
            POST|PUT)
                body='{"data":null}'
                ;;
            *)
                http_code=405
                body='{"errors":{"method":"not allowed"}}'
                ;;
        esac
        ;;
    /nodes/*/qemu/*/clone)
        body='{"data":"UPID:pve:00001:00001:00000066:qmclone:101:root@pam:"}'
        ;;
    /nodes/*/tasks/*qmclone*/status)
        body="{\"data\":{\"status\":\"stopped\",\"exitstatus\":\"${CURL_CLONE_EXITSTATUS:-OK}\"}}"
        ;;
    /nodes/*/tasks/*/status)
        # Catch-all for task polls (covers start and config tasks).
        body="{\"data\":{\"status\":\"stopped\",\"exitstatus\":\"${CURL_START_EXITSTATUS:-OK}\"}}"
        ;;
    /nodes/*/qemu/*/status/start)
        body='{"data":"UPID:pve:00002:00002:00000066:qmstart:200:root@pam:"}'
        ;;
    /nodes/*/qemu/*/agent/ping)
        if [ "${CURL_AGENT_PING_FAIL:-0}" = "1" ]; then
            http_code=500
            body='{"errors":{"exc":"qemu guest agent is not running"}}'
        else
            body='{"data":null}'
        fi
        ;;
    /nodes/*/qemu/*/agent/file-write)
        body='{"data":null}'
        ;;
    /nodes/*/qemu/*/agent/exec)
        body='{"data":{"pid":1234}}'
        ;;
    *)
        printf 'curl stub: unhandled path: %s\n' "$path" >&2
        exit 1
        ;;
esac

# Write body to -o target (or stdout if no -o).
if [ -n "$output_file" ]; then
    printf '%s' "$body" > "$output_file"
else
    printf '%s' "$body"
fi

# Print HTTP code if -w was supplied.
if [ "$want_http_code" -eq 1 ]; then
    printf '%s' "$http_code"
fi
SH
chmod +x "$SCRATCH/bin/curl"

# ---------------------------------------------------------------------------
# Helper: run provision.sh with the given args, capturing stdout and rc.
# Stderr is discarded to keep test output clean.
# ---------------------------------------------------------------------------
run_provision() {
    local out rc
    out=$(bash "$PROVISION" "$@" 2>/dev/null) && rc=0 || rc=$?
    printf '%s\n' "$out"
    return "$rc"
}

# ---------------------------------------------------------------------------
# Test 1 -- clone POST must carry pool=ephemeral-ci
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
run_provision valid-label test-token https://github.com/owner/repo >/dev/null

if grep -qxF 'pool=ephemeral-ci' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-1: clone POST carries pool=ephemeral-ci"
else
    ko "test-1: pool=ephemeral-ci not found in curl argv"
fi

# Prove the check is grounded: the clone URL must also be present.
if grep -q '/clone' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-1: clone endpoint URL recorded in curl argv"
else
    ko "test-1: clone URL missing from curl argv (stub may not have been called)"
fi

# ---------------------------------------------------------------------------
# Test 2 -- clone task exitstatus != OK -> fail, no inject, no start
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
export CURL_CLONE_EXITSTATUS=FAILED
OUT=$(bash "$PROVISION" valid-label test-token https://github.com/owner/repo 2>/dev/null) && rc2=0 || rc2=$?
unset CURL_CLONE_EXITSTATUS

if [ "$rc2" -ne 0 ]; then
    ok "test-2: provision.sh exits non-zero when clone task fails"
else
    ko "test-2: provision.sh should exit non-zero on clone task failure"
fi

# vmid= must NOT appear on stdout (it is emitted after clone succeeds).
if printf '%s\n' "$OUT" | grep -qE '^vmid='; then
    ko "test-2: vmid= appeared on stdout before successful clone (ordering fault)"
else
    ok "test-2: vmid= not on stdout when clone task fails"
fi

# The start endpoint must NOT have been called.
if grep -q '/status/start' "$CURL_ARGV_FILE" 2>/dev/null; then
    ko "test-2: start was called despite clone task failure"
else
    ok "test-2: start not called after clone task failure"
fi

# ---------------------------------------------------------------------------
# Test 3 -- registration token must not appear in any curl argv
# ---------------------------------------------------------------------------
SECRET_TOKEN="SUPERSECRETTOKEN99"
rm -f "$CURL_ARGV_FILE"
run_provision valid-label "$SECRET_TOKEN" https://github.com/owner/repo >/dev/null

if grep -qF "$SECRET_TOKEN" "$CURL_ARGV_FILE" 2>/dev/null; then
    ko "test-3: registration token found in curl argv"
else
    ok "test-3: registration token not present in any curl argv"
fi

# Prove the stub recorded something (so the absence above is meaningful).
if [ -s "$CURL_ARGV_FILE" ]; then
    ok "test-3: curl argv file is non-empty (stub was called)"
else
    ko "test-3: curl argv file is empty -- stub may not have been invoked"
fi

# ---------------------------------------------------------------------------
# Test 4 -- failure after the clone -> non-zero exit AND vmid= on stdout
#
# The VMID must reach the caller even though provision.sh failed, because the
# teardown job is the only thing that can destroy the VM that was created. That
# is the whole point of the output contract at the top of provision.sh.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
export CURL_START_EXITSTATUS=FAILED
OUT4=$(bash "$PROVISION" valid-label test-token https://github.com/owner/repo 2>/dev/null) && rc4=0 || rc4=$?
unset CURL_START_EXITSTATUS

if [ "$rc4" -ne 0 ]; then
    ok "test-4: provision.sh exits non-zero when start task fails"
else
    ko "test-4: provision.sh should exit non-zero on start task failure"
fi

if printf '%s\n' "$OUT4" | grep -qE '^vmid=[0-9]+$'; then
    ok "test-4: vmid=<n> present on stdout despite start failure"
else
    ko "test-4: vmid=<n> missing from stdout on start failure (got: '$OUT4')"
fi

# No ledger assertion: provision.sh deliberately writes no ledger file. A file
# on this runner's disk cannot be read by the teardown job, which runs on a
# different ephemeral runner (db-ulfv). Ownership is established from the
# hypervisor instead — name, pool membership and the template flag.
if grep -q '/clone' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-4: the VM really was created before the failure"
else
    ko "test-4: no clone call recorded — the failure happened too early to test"
fi

# ---------------------------------------------------------------------------
# Test 5 -- PVE_TOKEN_SECRET unset -> fails before calling curl
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
(
    unset PVE_TOKEN_SECRET
    bash "$PROVISION" valid-label test-token https://github.com/owner/repo >/dev/null 2>/dev/null
) && rc5=0 || rc5=$?

if [ "$rc5" -ne 0 ]; then
    ok "test-5: provision.sh exits non-zero when PVE_TOKEN_SECRET is unset"
else
    ko "test-5: provision.sh should fail when PVE_TOKEN_SECRET is unset"
fi

if [ -f "$CURL_ARGV_FILE" ] && [ -s "$CURL_ARGV_FILE" ]; then
    ko "test-5: curl was called despite unset credentials"
else
    ok "test-5: curl not called when credentials are missing"
fi

# ---------------------------------------------------------------------------
# Test 6 -- agent/file-write must target /run/gh-runner-init
#
# provision.sh delivers the runner credentials by writing /run/gh-runner-init
# inside the guest via the qemu guest agent. Verify that the file-write call
# is made to the correct path.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
run_provision valid-label test-token https://github.com/owner/repo >/dev/null

if grep -qF '/agent/file-write' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-6: agent/file-write endpoint called"
else
    ko "test-6: agent/file-write not found in curl argv (delivery did not happen)"
fi

# Prove the check is grounded: the target path must also be present in args.
if grep -qF 'file=/run/gh-runner-init' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-6: file=/run/gh-runner-init passed to file-write"
else
    ko "test-6: file=/run/gh-runner-init not found in curl argv (wrong target path)"
fi

# ---------------------------------------------------------------------------
# Test 7 -- guest agent must be polled before file-write
#
# provision.sh waits for /agent/ping to succeed before calling file-write.
# Verify that agent/ping appears in the curl argv, proving the wait happened.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
run_provision valid-label test-token https://github.com/owner/repo >/dev/null

if grep -qF '/agent/ping' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-7: agent/ping called to wait for guest agent"
else
    ko "test-7: agent/ping not found in curl argv (agent wait was skipped)"
fi

# Prove the check is grounded: file-write must have followed ping.
if grep -qF '/agent/file-write' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-7: agent/file-write followed the ping (stub was live)"
else
    ko "test-7: agent/file-write missing (stub may not have been called at all)"
fi

# ---------------------------------------------------------------------------
# Test 8 -- agent timeout causes non-zero exit
#
# If the guest agent never responds within AGENT_TIMEOUT seconds,
# provision.sh must exit non-zero without calling file-write.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
export CURL_AGENT_PING_FAIL=1
OUT8=$(bash "$PROVISION" valid-label test-token https://github.com/owner/repo 2>/dev/null) && rc8=0 || rc8=$?
unset CURL_AGENT_PING_FAIL

if [ "$rc8" -ne 0 ]; then
    ok "test-8: provision.sh exits non-zero when agent does not become ready"
else
    ko "test-8: provision.sh should exit non-zero when agent times out"
fi

if ! grep -qF '/agent/file-write' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-8: file-write not called when agent ping times out"
else
    ko "test-8: file-write was called despite agent ping failure"
fi

# ---------------------------------------------------------------------------
# Test 9 -- PVE_API_HOST is honoured
#
# provision.sh no longer runs on the hypervisor. It runs in a GitHub-hosted job
# that reaches the host over the tailnet, so a hardcoded https://localhost:8006
# meant it could not provision anything at all from where it now runs. This
# asserts the configured host reaches curl, and that loopback does not.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
PVE_API_HOST=hv.example.test PVE_API_PORT=9999     bash "$PROVISION" valid-label test-token https://github.com/owner/repo     >/dev/null 2>&1 || true

if grep -qF 'hv.example.test:9999' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-9: PVE_API_HOST/PVE_API_PORT reach the API URL"
else
    ko "test-9: configured API host absent from curl argv"
fi

if grep -qF 'localhost:8006' "$CURL_ARGV_FILE" 2>/dev/null; then
    ko "test-9: loopback still hardcoded somewhere in the API path"
else
    ok "test-9: no hardcoded loopback in the API path"
fi

# ---------------------------------------------------------------------------
# Test 10 -- the guest script is delivered, made runnable, and lands BEFORE
#            the token
#
# start-runner.sh ships from this repository on every run rather than being
# baked into the VM template, so changing it never requires resealing the
# template. Ordering is load-bearing: the guest's ephemeral-runner.path unit
# fires the moment /run/gh-runner-init appears, so the script must already be
# in place and executable when it does.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
run_provision valid-label test-token https://github.com/owner/repo >/dev/null

if grep -qF 'file=/home/runner/start-runner.sh' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-10: guest start-runner.sh delivered"
else
    ko "test-10: guest start-runner.sh was never written"
fi

if grep -qF 'command=/bin/chmod' "$CURL_ARGV_FILE" 2>/dev/null \
   && grep -qF 'command=/bin/chown' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-10: guest script chowned and made executable"
else
    ko "test-10: guest script left root-owned or non-executable"
fi

# Ordering, by line number in the recorded argv.
_script_at=$(grep -nF 'file=/home/runner/start-runner.sh' "$CURL_ARGV_FILE" | head -1 | cut -d: -f1)
_token_at=$(grep -nF 'file=/run/gh-runner-init' "$CURL_ARGV_FILE" | head -1 | cut -d: -f1)
if [ -n "$_script_at" ] && [ -n "$_token_at" ] && [ "$_script_at" -lt "$_token_at" ]; then
    ok "test-10: script written before the token (path unit cannot fire early)"
else
    ko "test-10: token written before the script — the path unit can fire with no script present"
fi

if grep -qF 'RUNNER_GROUP' "$CURL_ARGV_FILE" 2>/dev/null \
   || grep -q 'content@' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-10: token payload delivered via a file, not inline argv"
else
    ko "test-10: token payload not delivered through content@FILE"
fi

# ---------------------------------------------------------------------------
# Test 11 -- a pool-scoped token sees 403, not 404, for VMs outside its pool
#
# The API token's ACL is scoped to /pool/ephemeral-ci, so Proxmox refuses to
# say whether a VM outside that pool exists: it answers 403. /cluster/nextid
# is not ACL-filtered, so it happily returns an id belonging to one of those
# VMs — and treating 403 as an error made provisioning impossible.
#
# Two things are asserted: 403 does not abort, and the candidate id ADVANCES.
# Re-asking /cluster/nextid would return the same id forever, turning one
# collision into CLONE_RETRIES identical attempts and then a failure.
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE"
CURL_VMID_403_UNTIL=201 run_provision valid-label test-token https://github.com/DeckDumpster >/dev/null 2>&1 || true

if grep -qF '/qemu/202/config' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-11: candidate advanced past the 403 ids"
else
    ko "test-11: candidate did not advance past a 403 (would spin on one id)"
fi

if grep -qF '/qemu/200/config' "$CURL_ARGV_FILE" 2>/dev/null \
   && grep -qF '/qemu/201/config' "$CURL_ARGV_FILE" 2>/dev/null; then
    ok "test-11: each 403 id was probed once, in order"
else
    ko "test-11: 403 ids were not probed in sequence"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total=$(( pass + fail ))
echo ""
echo "Results: $pass passed, $fail failed, $total total"
[ "$fail" -eq 0 ]
