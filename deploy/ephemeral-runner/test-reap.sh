#!/usr/bin/env bash
# covers: deploy/ephemeral-runner/reap.sh deploy/ephemeral-runner/teardown.sh
#
# Regression suite for db-69kx: CRED_FILE sourcing and template-flag guard.
#
# Tests:
#   1. reap.sh skips a VM whose config carries template:1, even when its
#      VMID differs from TEMPLATE_VMID — the flag is a fact about the VM;
#      the id is configuration and can be wrong.
#   2. teardown.sh refuses a VM whose config carries template:1, even when
#      its VMID differs from TEMPLATE_VMID.
#   3. TEMPLATE_VMID set in CRED_FILE reaches reap.sh (sourcing works).
#   4. TEMPLATE_VMID set in CRED_FILE reaches teardown.sh (sourcing works).
#
# Run: bash deploy/ephemeral-runner/test-reap.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAP="$SCRIPT_DIR/reap.sh"
TEARDOWN="$SCRIPT_DIR/teardown.sh"

PASS=0
FAIL=0

TMPDIR_ROOT=$(mktemp -d)
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

_pass() { (( PASS++ )) || true; echo "  PASS: $1"; }
_fail() { (( FAIL++ )) || true; echo "  FAIL: $1"; }

# ---------------------------------------------------------------------------
# Teardown mock infrastructure (mirrors test-teardown.sh)
# ---------------------------------------------------------------------------

_td_setup() {
    TD_DIR=$(mktemp -d -p "$TMPDIR_ROOT")
    SNIPPETS_DIR="$TD_DIR/snippets"
    mkdir -p "$SNIPPETS_DIR"
    PVAPI_LOG="$TD_DIR/pvapi.log"
    PVAPI_CALL_FILE="$TD_DIR/call_count"
    PVAPI_RESPONSES="$TD_DIR/responses"
    mkdir -p "$PVAPI_RESPONSES"
    printf '0' > "$PVAPI_CALL_FILE"
    PVAPI_SH="$TD_DIR/pvapi.sh"
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

_td_resp() {
    local n="$1" status="$2" body="${3:-}"
    [ -z "$body" ] && body='{}'
    printf '%s\n%s\n' "$status" "$body" > "${PVAPI_RESPONSES}/${n}"
}

_td_log_has() {
    grep -q "$1" "$PVAPI_LOG" 2>/dev/null
}

# Run teardown.sh with the test fixtures, passing all env vars explicitly.
# Accepts additional KEY=VALUE pairs as arguments to inject.
_run_teardown() {
    local vmid="$1"; shift
    local extra_env=("$@")
    env \
    PVAPI_SH="$PVAPI_SH" \
    PVAPI_LOG="$PVAPI_LOG" \
    PVAPI_CALL_FILE="$PVAPI_CALL_FILE" \
    PVAPI_RESPONSES="$PVAPI_RESPONSES" \
    SNIPPETS_DIR="$SNIPPETS_DIR" \
    TEMPLATE_VMID="${TEMPLATE_VMID:-101}" \
    PVE_HOST=pve-test \
    PVE_NODE=pve \
    PVE_API_TOKEN_ID=test@pve!tok \
    PVE_API_TOKEN_SECRET=00000000-0000-0000-0000-000000000000 \
    STOP_TIMEOUT=1 \
    STOP_POLL_INTERVAL=0 \
    FORCE_STOP_WAIT=0 \
    "${extra_env[@]}" \
    bash "$TEARDOWN" "$vmid"
}

# ---------------------------------------------------------------------------
# reap.sh mock infrastructure
#
# reap.sh's pvapi() calls curl directly. We stub curl on PATH using a
# URL-pattern dispatcher so tests can set up responses per-endpoint.
# ---------------------------------------------------------------------------

_reap_setup() {
    RD=$(mktemp -d -p "$TMPDIR_ROOT")
    REAP_SNIPPETS="$RD/snippets"
    mkdir -p "$REAP_SNIPPETS"
    BIN="$RD/bin"
    mkdir -p "$BIN"
    # Each stub file is placed at $BIN/.stub-<key>; curl reads them by URL pattern.
    printf '{"data":[]}\n' > "$BIN/.stub-qemu-list"
    printf '{"data":{"name":"gh-runner-500","meta":"ctime=1000000000"}}\n' > "$BIN/.stub-qemu-config"
    printf '{"data":"UPID:pve:1:1:1:stop:500:root@pam:"}\n' > "$BIN/.stub-stop"
    printf '{"data":{"status":"stopped"}}\n' > "$BIN/.stub-current"
    cat > "$BIN/curl" <<'STUB'
#!/usr/bin/env bash
url=""
for arg in "$@"; do
    case "$arg" in https://*) url="$arg" ;; esac
done
path="${url#https://}"
path="${path#*/api2/json}"
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$path" =~ /qemu/[0-9]+/config ]]; then
    cat "$BIN_DIR/.stub-qemu-config"
elif [[ "$path" =~ /qemu/[0-9]+/status/current ]]; then
    cat "$BIN_DIR/.stub-current"
elif [[ "$path" =~ /qemu/[0-9]+/status/stop ]]; then
    cat "$BIN_DIR/.stub-stop"
elif [[ "$path" =~ purge ]]; then
    echo '{"data":"UPID:pve:2:2:2:destroy:500:root@pam:"}'
elif [[ "$path" =~ /nodes/[^/]+/qemu$ ]]; then
    cat "$BIN_DIR/.stub-qemu-list"
else
    printf 'curl stub: unhandled path: %s\n' "$path" >&2
    exit 1
fi
STUB
    chmod +x "$BIN/curl"
}

# Run reap.sh with the current test fixtures. Pass extra KEY=VALUE pairs as args.
_run_reap() {
    local extra_env=()
    # Collect leading KEY=VALUE args.
    while [[ $# -gt 0 && "$1" == *=* ]]; do
        extra_env+=("$1")
        shift
    done
    PATH="$BIN:$PATH" \
    SNIPPETS_DIR="$REAP_SNIPPETS" \
    TEMPLATE_VMID="${TEMPLATE_VMID:-101}" \
    PVE_NODE=pve \
    PVE_TOKEN_ID=test@pve!tok \
    PVE_TOKEN_SECRET=00000000-0000-0000-0000-000000000000 \
    GITHUB_TOKEN="" \
    GH_REPO="" \
    "${extra_env[@]+"${extra_env[@]}"}" \
    bash "$REAP" "$@"
}

# ============================================================
# TEST 1: reap.sh skips a VM whose config carries template:1,
#         even when that VMID does not equal TEMPLATE_VMID.
#
# TEMPLATE_VMID=101 (the wrong default). The real template is VMID 9100
# and its Proxmox config carries template:1. The old code only checked
# whether VMID==TEMPLATE_VMID; since 9100!=101 it would proceed to destroy.
# The fix adds a template-flag check on the config before the age/busy path.
# ============================================================
echo "--- Test 1: reap.sh skips VM with template:1 (VMID != TEMPLATE_VMID)"
(
    _reap_setup
    # VM list: one VM at 9100, carrying template:1 (as Proxmox reports it).
    printf '{"data":[{"vmid":9100,"name":"gh-runner-9100","template":1}]}\n' > "$BIN/.stub-qemu-list"
    # Config: template:1, old ctime — would be reaped on age alone without the flag check.
    printf '{"data":{"name":"gh-runner-9100","template":1,"meta":"creation-qemu=9.0.0,ctime=1000000000"}}\n' \
        > "$BIN/.stub-qemu-config"
    TEMPLATE_VMID=101  # default/wrong value

    output=$(TEMPLATE_VMID=101 _run_reap --dry-run 2>&1 || true)

    if printf '%s\n' "$output" | grep -q 'would destroy.*9100'; then
        echo "  expected fail: reap.sh would destroy VM 9100 (template:1 flag not checked)" >&2
        exit 1
    fi
    # After fix, reap.sh must log that 9100 is a template or was skipped as one.
    printf '%s\n' "$output" | grep -qiE 'template.*9100|9100.*template|skipping.*9100' || {
        echo "  expected fail: reap.sh did not log a template-skip for VMID 9100" >&2
        exit 1
    }
) && _pass "Test 1: reap.sh skips VM with template:1" || _fail "Test 1: reap.sh skips VM with template:1"

# ============================================================
# TEST 2: teardown.sh refuses a VM whose config carries template:1,
#         even when its VMID differs from TEMPLATE_VMID.
#
# All other guards are satisfied (name matches, stop succeeds)
# so the only thing preventing destruction should be template:1.
# The test must red with the current code (no template-flag guard) and
# green after the fix.
# ============================================================
echo "--- Test 2: teardown.sh refuses VM with template:1 (VMID != TEMPLATE_VMID)"
(
    _td_setup
    VMID=9100
    TEMPLATE_VMID=101

    # Call 1: GET /config → 200, correct name, but template:1.
    _td_resp 1 200 '{"data":{"name":"gh-runner-9100","template":1}}'
    # Calls 2-5 are reached only if the template guard does not fire.
    _td_resp 2 200 '{"data":"UPID:pve:00001234:abcdef01:67890abc:stopvm:9100:root@pam:"}'
    _td_resp 3 200 '{"data":{"status":"stopped","exitstatus":"OK"}}'
    _td_resp 4 200 '{"data":{"status":"stopped"}}'
    _td_resp 5 200 '{"data":"UPID:pve:00001235:abcdef02:67890abd:qmdestroy:9100:root@pam:"}'

    rc=0
    TEMPLATE_VMID=101 _run_teardown $VMID >/dev/null 2>&1 || rc=$?

    [ "$rc" -ne 0 ] || {
        echo "  expected fail: teardown.sh returned 0 for a VM with template:1" >&2
        exit 1
    }
    ! _td_log_has "PVAPI:DELETE:" || {
        echo "  expected fail: teardown.sh issued a DELETE for a VM with template:1" >&2
        exit 1
    }
) && _pass "Test 2: teardown.sh refuses VM with template:1" || _fail "Test 2: teardown.sh refuses VM with template:1"

# ============================================================
# TEST 3: TEMPLATE_VMID set in CRED_FILE reaches reap.sh.
#
# The old bug: reap.sh never sourced CRED_FILE, so TEMPLATE_VMID=9100 in
# /etc/gh-ephemeral-runner/token was invisible — the variable kept its
# default 101 and the real template at VMID 9100 was treated as a clone.
# ============================================================
echo "--- Test 3: TEMPLATE_VMID from CRED_FILE reaches reap.sh"
(
    _reap_setup
    CRED_FILE="$RD/token"
    printf 'TEMPLATE_VMID=9100\n' > "$CRED_FILE"

    # A single VM at 9100 with an old ctime — would be reaped without CRED_FILE.
    printf '{"data":[{"vmid":9100,"name":"gh-runner-9100"}]}\n' > "$BIN/.stub-qemu-list"
    printf '{"data":{"name":"gh-runner-9100","meta":"creation-qemu=9.0.0,ctime=1000000000"}}\n' \
        > "$BIN/.stub-qemu-config"

    # Do NOT set TEMPLATE_VMID — it must come from CRED_FILE only.
    output=$(
        PATH="$BIN:$PATH" \
            SNIPPETS_DIR="$REAP_SNIPPETS" \
        CRED_FILE="$CRED_FILE" \
        PVE_NODE=pve \
        PVE_TOKEN_ID=test@pve!tok \
        PVE_TOKEN_SECRET=00000000-0000-0000-0000-000000000000 \
        GITHUB_TOKEN="" \
        GH_REPO="" \
        bash "$REAP" --dry-run 2>&1 || true
    )

    if printf '%s\n' "$output" | grep -q 'would destroy.*9100'; then
        echo "  expected fail: TEMPLATE_VMID from CRED_FILE did not reach reap.sh — would destroy 9100" >&2
        exit 1
    fi
    # After fix, reap.sh must log "skipping template VMID 9100".
    printf '%s\n' "$output" | grep -qiE 'skipping template.*9100|template.*9100' || {
        echo "  expected fail: reap.sh did not log a template-skip for 9100 — CRED_FILE not sourced" >&2
        exit 1
    }
) && _pass "Test 3: TEMPLATE_VMID from CRED_FILE reaches reap.sh" || _fail "Test 3: TEMPLATE_VMID from CRED_FILE reaches reap.sh"

# ============================================================
# TEST 4: TEMPLATE_VMID set in CRED_FILE reaches teardown.sh.
#
# Without sourcing CRED_FILE, teardown.sh uses TEMPLATE_VMID=101.
# VMID 9100 then clears guard 2 (9100 != 101). After the fix, teardown.sh
# sources CRED_FILE, reads TEMPLATE_VMID=9100, and guard 2 fires before
# any API call is made.
# ============================================================
echo "--- Test 4: TEMPLATE_VMID from CRED_FILE reaches teardown.sh"
(
    _td_setup
    VMID=9100
    CRED_FILE="$TD_DIR/token"
    printf 'TEMPLATE_VMID=9100\n' > "$CRED_FILE"

    # Responses for the full stop/destroy path — reached only without guard 2.
    _td_resp 1 200 '{"data":{"name":"gh-runner-9100"}}'
    _td_resp 2 200 '{"data":"UPID:pve:00001234:abcdef01:67890abc:stopvm:9100:root@pam:"}'
    _td_resp 3 200 '{"data":{"status":"stopped","exitstatus":"OK"}}'
    _td_resp 4 200 '{"data":{"status":"stopped"}}'
    _td_resp 5 200 '{"data":"UPID:pve:00001235:abcdef02:67890abd:qmdestroy:9100:root@pam:"}'

    rc=0
    env \
    PVAPI_SH="$PVAPI_SH" \
    PVAPI_LOG="$PVAPI_LOG" \
    PVAPI_CALL_FILE="$PVAPI_CALL_FILE" \
    PVAPI_RESPONSES="$PVAPI_RESPONSES" \
    SNIPPETS_DIR="$SNIPPETS_DIR" \
    CRED_FILE="$CRED_FILE" \
    PVE_HOST=pve-test \
    PVE_NODE=pve \
    PVE_API_TOKEN_ID=test@pve!tok \
    PVE_API_TOKEN_SECRET=00000000-0000-0000-0000-000000000000 \
    STOP_TIMEOUT=1 \
    STOP_POLL_INTERVAL=0 \
    FORCE_STOP_WAIT=0 \
    bash "$TEARDOWN" $VMID >/dev/null 2>&1 || rc=$?

    # teardown.sh must refuse because CRED_FILE says 9100 is the template.
    [ "$rc" -ne 0 ] || {
        echo "  expected fail: teardown.sh returned 0 — CRED_FILE not sourced, guard 2 did not fire" >&2
        exit 1
    }
    ! _td_log_has "PVAPI:DELETE:" || {
        echo "  expected fail: teardown.sh issued a DELETE — guard 2 did not block it" >&2
        exit 1
    }
) && _pass "Test 4: TEMPLATE_VMID from CRED_FILE reaches teardown.sh" || _fail "Test 4: TEMPLATE_VMID from CRED_FILE reaches teardown.sh"

# ============================================================
# Summary
# ============================================================
echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
