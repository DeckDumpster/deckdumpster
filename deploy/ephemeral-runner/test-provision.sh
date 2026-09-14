#!/usr/bin/env bash
# covers: deploy/ephemeral-runner/provision.sh
#
# Tests for the four faults fixed in db-oh4:
#   1. SSH must pass UserKnownHostsFile=/dev/null (known_hosts pollution)
#   2. Guest IP filter must skip container bridge addresses/interfaces
#   3. A label with shell-special characters must be rejected
#   4. vmid=<n> must appear on stdout even when registration fails
#
# No hypervisor required. qm and ssh are stubbed on PATH.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROVISION="$SCRIPT_DIR/provision.sh"

pass=0
fail=0

ok() { echo "PASS: $1"; (( pass++ )) || true; }
ko() { echo "FAIL: $1"; (( fail++ )) || true; }

# Build a throwaway scratch directory and put stubs on PATH.
SCRATCH=$(mktemp -d)
mkdir -p "$SCRATCH/bin"
trap 'rm -rf "$SCRATCH"' EXIT

export PATH="$SCRATCH/bin:$PATH"
export LEDGER_FILE="$SCRATCH/ledger"
export RUNNER_SSH_KEY="$SCRATCH/fake-key"
export AGENT_TIMEOUT=5   # keep test fast; real timeout is 120s
touch "$RUNNER_SSH_KEY" && chmod 600 "$RUNNER_SSH_KEY"

# ---------------------------------------------------------------------------
# Stub: qm
# ---------------------------------------------------------------------------
# nextid → 200
# config 200 → exit 1 (VMID is free)
# clone / start → succeed
# guest cmd ping → succeed
# guest cmd network-get-interfaces → emit a JSON fixture (set per-test via
#   QM_NETIF_JSON; defaults to a clean single-interface answer)
cat >"$SCRATCH/bin/qm" <<'SH'
#!/usr/bin/env bash
# Default network-get-interfaces JSON; tests override via QM_NETIF_JSON.
# Not embedded as ${var:-complex-json}: bash counts braces lexically when
# scanning the parameter expansion default, so a default value with multiple
# balanced brace pairs closes at the wrong one.
_DEFAULT_NETIF='{"result":[{"name":"ens18","ip-addresses":[{"ip-address-type":"ipv4","ip-address":"192.168.1.50"}]}]}'
case "$1" in
    nextid) echo 200 ;;
    config) exit 1 ;;
    clone)  ;;
    start)  ;;
    guest)
        # argv: qm guest cmd <VMID> <subcommand>
        # shift past "guest", "cmd", and the VMID to reach the subcommand.
        shift  # drop "guest"
        case "$1" in
            cmd)
                shift  # drop "cmd"
                shift  # drop VMID
                case "$1" in
                    ping) ;;
                    network-get-interfaces)
                        if [ -n "${QM_NETIF_JSON:-}" ]; then
                            echo "$QM_NETIF_JSON"
                        else
                            echo "$_DEFAULT_NETIF"
                        fi
                        ;;
                    *) echo "qm stub: unknown guest cmd $1" >&2; exit 1 ;;
                esac ;;
            *) echo "qm stub: unknown guest subcommand $1" >&2; exit 1 ;;
        esac ;;
    *) echo "qm stub: unknown command $1" >&2; exit 1 ;;
esac
SH
chmod +x "$SCRATCH/bin/qm"

# ---------------------------------------------------------------------------
# Stub: ssh (base — records its argv for inspection, then succeeds)
# ---------------------------------------------------------------------------
# Per-test behaviour is controlled by SSH_STUB_EXIT (default 0).
# Bake $SCRATCH into the stub with printf so the path is resolved at
# stub-write time rather than depending on env propagation at runtime.
# %%s  → literal %s in the output (for the inner printf format string)
# \\n  → literal \n in the output (for the inner printf newline escape)
SSH_ARGV_FILE="$SCRATCH/ssh-argv"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" > "%s"\nexit "${SSH_STUB_EXIT:-0}"\n' \
    "$SSH_ARGV_FILE" >"$SCRATCH/bin/ssh"
chmod +x "$SCRATCH/bin/ssh"
export SCRATCH

# ---------------------------------------------------------------------------
# Test 1 — SSH argv must contain UserKnownHostsFile=/dev/null  (fault 1)
# ---------------------------------------------------------------------------
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
OUT=$(bash "$PROVISION" valid-label unused-token https://github.com/owner/repo 2>/dev/null)

if grep -qF 'UserKnownHostsFile=/dev/null' "$SCRATCH/ssh-argv" 2>/dev/null; then
    ok "fault-1: ssh receives UserKnownHostsFile=/dev/null"
else
    ko "fault-1: ssh does NOT receive UserKnownHostsFile=/dev/null"
fi

# Also assert LogLevel=ERROR is present (suppresses the TOFU warning line).
if grep -qF 'LogLevel=ERROR' "$SCRATCH/ssh-argv" 2>/dev/null; then
    ok "fault-1: ssh receives LogLevel=ERROR"
else
    ko "fault-1: ssh does NOT receive LogLevel=ERROR"
fi

# ---------------------------------------------------------------------------
# Test 2 — podman0 before ens18: script must pick ens18  (fault 2)
# ---------------------------------------------------------------------------
# The fixture places podman0 (10.88.0.1) first, then ens18 (192.168.1.50).
# The script must skip podman0 and select ens18.
PODMAN0_FIRST='{
  "result": [
    {"name":"podman0","ip-addresses":[{"ip-address-type":"ipv4","ip-address":"10.88.0.1"}]},
    {"name":"ens18","ip-addresses":[{"ip-address-type":"ipv4","ip-address":"192.168.1.50"}]}
  ]
}'

rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
export QM_NETIF_JSON="$PODMAN0_FIRST"
if OUT=$(bash "$PROVISION" valid-label unused-token https://github.com/owner/repo 2>/dev/null); then
    if grep -qF '192.168.1.50' "$SCRATCH/ssh-argv" 2>/dev/null; then
        ok "fault-2: ens18 (192.168.1.50) selected when podman0 is listed first"
    else
        ko "fault-2: wrong IP selected — expected 192.168.1.50 in ssh argv"
    fi
else
    ko "fault-2: provision.sh failed unexpectedly"
fi
unset QM_NETIF_JSON

# Prove the filter would have caught podman0: run with ONLY podman0 present.
ONLY_PODMAN0='{
  "result": [
    {"name":"podman0","ip-addresses":[{"ip-address-type":"ipv4","ip-address":"10.88.0.1"}]}
  ]
}'
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
export QM_NETIF_JSON="$ONLY_PODMAN0"
if bash "$PROVISION" valid-label unused-token https://github.com/owner/repo >/dev/null 2>/dev/null; then
    ko "fault-2: provision.sh should have failed when only podman0 is present"
else
    ok "fault-2: provision.sh correctly fails when only container bridge IP is present"
fi
unset QM_NETIF_JSON

# Also verify docker0 in 172.17.x.x range is excluded.
DOCKER0_ONLY='{
  "result": [
    {"name":"docker0","ip-addresses":[{"ip-address-type":"ipv4","ip-address":"172.17.0.1"}]}
  ]
}'
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
export QM_NETIF_JSON="$DOCKER0_ONLY"
if bash "$PROVISION" valid-label unused-token https://github.com/owner/repo >/dev/null 2>/dev/null; then
    ko "fault-2: provision.sh should have failed when only docker0 is present"
else
    ok "fault-2: provision.sh correctly fails when only docker0 IP (172.17.x.x) is present"
fi
unset QM_NETIF_JSON

# ---------------------------------------------------------------------------
# Test 3 — label with ; must be rejected before SSH  (fault 3)
# ---------------------------------------------------------------------------
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
if bash "$PROVISION" "bad;label" unused-token https://github.com/owner/repo >/dev/null 2>/dev/null; then
    ko "fault-3: provision.sh should reject a label containing ';'"
else
    # Also confirm ssh was never called (label validation must be pre-SSH).
    if [ -f "$SCRATCH/ssh-argv" ]; then
        ko "fault-3: ssh was called despite invalid label"
    else
        ok "fault-3: label with ';' rejected before SSH"
    fi
fi

# Prove the validator can catch something: a valid label must be accepted.
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
if bash "$PROVISION" "ci-runner.1_ok-label" unused-token https://github.com/owner/repo >/dev/null 2>/dev/null; then
    ok "fault-3: valid label accepted"
else
    ko "fault-3: valid label incorrectly rejected"
fi

# ---------------------------------------------------------------------------
# Test 4 — vmid=<n> on stdout even when registration fails  (fault 4)
# ---------------------------------------------------------------------------
rm -f "$SCRATCH/ssh-argv" "$LEDGER_FILE"
export SSH_STUB_EXIT=1   # simulate registration failure
OUT=$(bash "$PROVISION" valid-label unused-token https://github.com/owner/repo 2>/dev/null) && rc=0 || rc=$?
unset SSH_STUB_EXIT

# The script exits non-zero when registration fails.
if [ "$rc" -ne 0 ]; then
    ok "fault-4: provision.sh exits non-zero on registration failure"
else
    ko "fault-4: provision.sh should exit non-zero when ssh fails"
fi

# The VMID must still appear on stdout.
if echo "$OUT" | grep -qE '^vmid=[0-9]+$'; then
    ok "fault-4: vmid=<n> present on stdout despite registration failure"
else
    ko "fault-4: vmid=<n> missing from stdout on registration failure (got: '$OUT')"
fi

# The ledger entry must also have been written.
if grep -qE '^200 ' "$LEDGER_FILE" 2>/dev/null; then
    ok "fault-4: ledger entry written despite registration failure"
else
    ko "fault-4: ledger entry missing after registration failure"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total=$(( pass + fail ))
echo ""
echo "Results: $pass passed, $fail failed, $total total"
[ "$fail" -eq 0 ]
