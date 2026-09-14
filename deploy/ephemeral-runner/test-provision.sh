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
#   4. failure after ledger write -> non-zero exit AND vmid=<n> on stdout
#      AND ledger line present
#   5. PVE_TOKEN_SECRET unset -> fails before calling curl, naming the cause
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROVISION="$SCRIPT_DIR/provision.sh"

pass=0
fail=0

ok() { echo "PASS: $1"; (( pass++ )) || true; }
ko() { echo "FAIL: $1"; (( fail++ )) || true; }

SCRATCH=$(mktemp -d)
mkdir -p "$SCRATCH/bin" "$SCRATCH/snippets"
trap 'rm -rf "$SCRATCH"' EXIT

export PATH="$SCRATCH/bin:$PATH"
export LEDGER_FILE="$SCRATCH/ledger"
export SNIPPETS_DIR="$SCRATCH/snippets"
export TASK_TIMEOUT=5
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
#   CURL_CLONE_EXITSTATUS  -- exitstatus in clone task poll response (default: OK)
#   CURL_START_EXITSTATUS  -- exitstatus in start task poll response (default: OK)
#   CURL_VMID_FREE_CODE    -- HTTP code for vmid free check (default: 404)
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
                http_code="${CURL_VMID_FREE_CODE:-404}"
                body='{"errors":{"vmid":"VM 200 not found"}}'
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
rm -f "$CURL_ARGV_FILE" "$LEDGER_FILE"
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
rm -f "$CURL_ARGV_FILE" "$LEDGER_FILE"
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
rm -f "$CURL_ARGV_FILE" "$LEDGER_FILE"
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
# Test 4 -- failure after ledger write -> non-zero exit AND vmid= on stdout
#           AND ledger line present
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE" "$LEDGER_FILE"
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

if grep -qE '^200 ' "$LEDGER_FILE" 2>/dev/null; then
    ok "test-4: ledger entry written despite start failure"
else
    ko "test-4: ledger entry missing after start failure"
fi

# ---------------------------------------------------------------------------
# Test 5 -- PVE_TOKEN_SECRET unset -> fails before calling curl
# ---------------------------------------------------------------------------
rm -f "$CURL_ARGV_FILE" "$LEDGER_FILE"
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
# Summary
# ---------------------------------------------------------------------------
total=$(( pass + fail ))
echo ""
echo "Results: $pass passed, $fail failed, $total total"
[ "$fail" -eq 0 ]
