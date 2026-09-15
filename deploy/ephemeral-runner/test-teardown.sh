#!/usr/bin/env bash
# covers: deploy/ephemeral-runner/teardown.sh
#
# Stubs the Proxmox API via PVAPI_SH so no hypervisor is required.
# Each test writes per-call responses into a directory; the mock pvapi()
# reads them in sequence and logs every call so assertions can verify
# which API calls were (and were not) made.
#
# Run: bash deploy/ephemeral-runner/test-teardown.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEARDOWN="$SCRIPT_DIR/teardown.sh"

PASS=0
FAIL=0

_die() { echo "FATAL: $*" >&2; exit 1; }

# --- Test infrastructure ---

TMPDIR_ROOT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

_setup() {
    # Create a fresh test directory. Sets:
    #   TDIR          — per-test temp directory
    #   LEDGER_FILE   — ledger path for this test
    #   PVAPI_LOG     — file recording every pvapi call (method:path:body)
    #   PVAPI_CALL_FILE — file holding the current call count
    #   PVAPI_RESPONSES — directory; file N holds status\nbody for call N
    #   PVAPI_SH      — path to the mock pvapi.sh for this test
    TDIR=$(mktemp -d -p "$TMPDIR_ROOT")
    LEDGER_FILE="$TDIR/ledger"
    PVAPI_LOG="$TDIR/pvapi.log"
    PVAPI_CALL_FILE="$TDIR/call_count"
    PVAPI_RESPONSES="$TDIR/responses"
    mkdir -p "$PVAPI_RESPONSES"
    printf '0' > "$PVAPI_CALL_FILE"
    PVAPI_SH="$TDIR/pvapi.sh"
    # Write the mock pvapi.sh. It reads sequenced response files; when a
    # response file is absent it defaults to HTTP 200 with an empty body.
    cat > "$PVAPI_SH" <<'MOCK'
PVAPI_STATUS=""
PVAPI_BODY=""
pvapi() {
    local method="$1" path="$2" body="${3:-}"
    PVAPI_STATUS=""
    PVAPI_BODY=""
    local count
    count=$(cat "${PVAPI_CALL_FILE}")
    count=$(( count + 1 ))
    printf '%d' "$count" > "${PVAPI_CALL_FILE}"
    printf 'PVAPI:%s:%s:%s\n' "$method" "$path" "$body" >> "${PVAPI_LOG}"
    local resp_file="${PVAPI_RESPONSES}/${count}"
    if [ -f "$resp_file" ]; then
        PVAPI_STATUS=$(head -1 "$resp_file")
        PVAPI_BODY=$(tail -n +2 "$resp_file")
    else
        PVAPI_STATUS="200"
        PVAPI_BODY='{}'
    fi
}
MOCK
}

_resp() {
    # _resp <call_number> <http_status> [body]
    local n="$1" status="$2" body="${3:-}"
    [ -z "$body" ] && body='{}'
    printf '%s\n%s\n' "$status" "$body" > "${PVAPI_RESPONSES}/${n}"
}

_ledger_add() {
    local vmid="$1"
    printf '%s some-label 1725000000\n' "$vmid" >> "$LEDGER_FILE"
}

_call_count() {
    cat "$PVAPI_CALL_FILE"
}

_log_has() {
    # _log_has <pattern> — true if the pvapi log contains the pattern
    grep -q "$1" "$PVAPI_LOG" 2>/dev/null
}

_assert_eq() {
    local label="$1" got="$2" expected="$3"
    if [ "$got" = "$expected" ]; then
        return 0
    fi
    echo "  FAIL: $label: got '$got', expected '$expected'" >&2
    return 1
}

_run_teardown() {
    # Run teardown.sh with the current test fixtures; returns its exit code.
    # All API env vars are set; STOP_TIMEOUT/POLL/WAIT are minimised so
    # timeout tests do not take seconds.
    PVAPI_SH="$PVAPI_SH" \
    PVAPI_LOG="$PVAPI_LOG" \
    PVAPI_CALL_FILE="$PVAPI_CALL_FILE" \
    PVAPI_RESPONSES="$PVAPI_RESPONSES" \
    LEDGER_FILE="$LEDGER_FILE" \
    TEMPLATE_VMID="${TEMPLATE_VMID:-101}" \
    PVE_API_HOST=pve-test \
    PVE_NODE=pve \
    PVE_TOKEN_ID=test@pve!tok \
    PVE_TOKEN_SECRET=00000000-0000-0000-0000-000000000000 \
    STOP_TIMEOUT="${STOP_TIMEOUT:-1}" \
    STOP_POLL_INTERVAL=0 \
    FORCE_STOP_WAIT=0 \
    bash "$TEARDOWN" "$@"
}

_pass() { (( PASS++ )) || true; echo "  PASS: $1"; }
_fail() { (( FAIL++ )) || true; echo "  FAIL: $1"; }

_check() {
    # _check <label> <exit_code_assertion> <assertion_commands...>
    # Runs the named check and records pass/fail.
    local label="$1"
    if "$@"; then
        _pass "$label"
    else
        _fail "$label"
    fi
}

# --- Helpers that each test uses as assertions ---

_assert_rc() { local label="$1" rc="$2" expected="$3"; _assert_eq "$label" "$rc" "$expected"; }

_assert_log_has()    { _log_has "$1" || { echo "  FAIL: expected API call matching '$1' not found" >&2; return 1; }; }
_assert_log_not_has() { ! _log_has "$1" || { echo "  FAIL: unexpected API call matching '$1' found in log" >&2; return 1; }; }
_assert_ledger_empty() {
    local vmid="$1"
    if grep -q "^${vmid} " "$LEDGER_FILE" 2>/dev/null; then
        echo "  FAIL: ledger still contains VMID $vmid" >&2
        return 1
    fi
}
_assert_ledger_has() {
    local vmid="$1"
    grep -q "^${vmid} " "$LEDGER_FILE" 2>/dev/null || {
        echo "  FAIL: ledger does not contain VMID $vmid" >&2
        return 1
    }
}
# ============================================================
# TEST 1: normal teardown of a live, ledger-backed VM
# ============================================================
# Plant a real destroy call first so tests 3/4 can rely on its absence
# as a meaningful signal (not just "nothing happened yet").
echo "--- Test 1: live VM, ledger-backed → rc=0, VM destroyed, ledger cleared"
(
    _setup
    VMID=500
    _ledger_add $VMID
    # Call 1: GET /config → 200, VM exists with correct name
    _resp 1 200 '{"data":{"name":"gh-runner-500","cores":2}}'
    # Call 2: POST /status/stop → 200, UPID
    _resp 2 200 '{"data":"UPID:pve:00001234:abcdef01:67890abc:stopvm:500:root@pam:"}'
    # Call 3: GET /tasks/.../status → stopped/OK
    _resp 3 200 '{"data":{"status":"stopped","exitstatus":"OK"}}'
    # Call 4: GET /status/current → stopped
    _resp 4 200 '{"data":{"status":"stopped"}}'
    # Call 5: DELETE → 200
    _resp 5 200 '{"data":"UPID:pve:00001235:abcdef02:67890abd:qmdestroy:500:root@pam:"}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    _assert_rc "exit code" "$rc" 0 \
    && _assert_log_has "PVAPI:DELETE:" \
    && _assert_ledger_empty $VMID
) && _pass "Test 1" || _fail "Test 1"

# ============================================================
# TEST 2: same VMID torn down a second time → rc=0 (idempotency)
#
# The first teardown removed the ledger line. The VM is now gone (API 404).
# The old bug: guard 2 (ledger) ran before the already-gone check, so the
# second call hit "VMID not found in ledger — refusing" and exited 1.
# ============================================================
echo "--- Test 2: second teardown of same VMID → rc=0 (idempotency)"
(
    _setup
    VMID=500
    # Ledger is empty — first teardown already removed the line.
    # Call 1: GET /config → 404 (VM is gone)
    _resp 1 404 '{"errors":{"vmid":"not found"}}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    _assert_rc "exit code" "$rc" 0 \
    && _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 2" || _fail "Test 2"

# ============================================================
# TEST 3: VMID present on host but absent from ledger → rc≠0, no destroy
# ============================================================
echo "--- Test 3: VM exists but not in ledger → rc≠0, no destroy"
(
    _setup
    VMID=500
    # Ledger does not contain this VMID.
    # Call 1: GET /config → 200 (VM exists)
    _resp 1 200 '{"data":{"name":"gh-runner-500","cores":2}}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero exit code, got 0" >&2; exit 1; }
    _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 3" || _fail "Test 3"

# ============================================================
# TEST 4: qm stop leaves VM running → script does not call destroy
#
# The old bug: qm stop ... || true discarded whether the VM was still running,
# so qm destroy was called on a running VM and was refused.
# ============================================================
echo "--- Test 4: stop leaves VM running → no destroy, reports it"
(
    _setup
    VMID=500
    _ledger_add $VMID
    # Call 1: GET /config → 200
    _resp 1 200 '{"data":{"name":"gh-runner-500","cores":2}}'
    # Call 2: POST /status/stop → 200
    _resp 2 200 '{"data":"UPID:pve:00001234:abcdef01:67890abc:stopvm:500:root@pam:"}'
    # Call 3: GET /tasks/.../status → still running (triggers timeout immediately
    # since STOP_TIMEOUT=1 and STOP_POLL_INTERVAL=0)
    _resp 3 200 '{"data":{"status":"running"}}'
    # Call 4: force-stop POST → 200
    _resp 4 200 '{"data":"UPID:pve:00001234:abcdef01:67890abc:stopvm:500:root@pam:"}'
    # Call 5: GET /status/current after force-stop → still running
    _resp 5 200 '{"data":{"status":"running"}}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero exit when VM still running" >&2; exit 1; }
    _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 4" || _fail "Test 4"

# ============================================================
# TEST 5: TEMPLATE_VMID → rc≠0, no API calls at all
# ============================================================
echo "--- Test 5: TEMPLATE_VMID → rc≠0, API never called"
(
    _setup
    VMID=101  # matches default TEMPLATE_VMID

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero exit for template VMID" >&2; exit 1; }
    _assert_eq "call count" "$(_call_count)" "0"
) && _pass "Test 5" || _fail "Test 5"

# ============================================================
# TEST 6: wrong VM name → rc≠0, destroy never called
#
# These two names are the other load-bearing VMs on this hypervisor.
# ============================================================
echo "--- Test 6a: VM named 'Agent-Swarm' → rc≠0, no destroy"
(
    _setup
    VMID=500
    _ledger_add $VMID
    _resp 1 200 '{"data":{"name":"Agent-Swarm","cores":8}}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero for wrong name" >&2; exit 1; }
    _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 6a" || _fail "Test 6a"

echo "--- Test 6b: VM named 'Prod-Services' → rc≠0, no destroy"
(
    _setup
    VMID=500
    _ledger_add $VMID
    _resp 1 200 '{"data":{"name":"Prod-Services","cores":8}}'

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero for wrong name" >&2; exit 1; }
    _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 6b" || _fail "Test 6b"

# ============================================================
# TEST 7: API connection error → rc≠0, no destroy
# ============================================================
echo "--- Test 7: connection error (curl failure) → rc≠0"
(
    _setup
    VMID=500
    _ledger_add $VMID
    # Override pvapi.sh to simulate curl exit 7 (connection refused).
    cat > "$PVAPI_SH" <<'MOCK'
PVAPI_STATUS=""
PVAPI_BODY=""
pvapi() {
    local method="$1" path="$2" body="${3:-}"
    PVAPI_STATUS=""
    PVAPI_BODY=""
    printf 'PVAPI:%s:%s:%s\n' "$method" "$path" "$body" >> "${PVAPI_LOG}"
    return 7
}
MOCK

    rc=0
    _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero on connection error" >&2; exit 1; }
    _assert_log_not_has "PVAPI:DELETE:"
) && _pass "Test 7" || _fail "Test 7"

# ============================================================
# TEST 8: non-numeric VMID → rc≠0, no API call
# ============================================================
echo "--- Test 8: non-numeric VMID → rc≠0"
(
    _setup
    rc=0
    _run_teardown "abc" >/dev/null 2>&1 || rc=$?
    [ "$rc" -ne 0 ] || { echo "  FAIL: expected non-zero for non-numeric VMID" >&2; exit 1; }
    _assert_eq "call count" "$(_call_count)" "0"
) && _pass "Test 8" || _fail "Test 8"

# ============================================================
# Summary
# ============================================================
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
