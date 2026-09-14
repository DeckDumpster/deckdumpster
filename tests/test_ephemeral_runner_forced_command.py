"""Tests for deploy/ephemeral-runner/forced-command.sh.

Stubs provision.sh, teardown.sh, and reap.sh so no Proxmox host is needed.
Drives the dispatcher by setting SSH_ORIGINAL_COMMAND directly in the
subprocess environment — no SSH, no network.

The critical property every refusal test asserts: the stub was never called.
A dispatcher that runs the command and then exits non-zero would pass an
exit-code-only test but fail here, because the stub's argv file stays empty
only if exec was never reached.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DISPATCHER = REPO_ROOT / "deploy" / "ephemeral-runner" / "forced-command.sh"

# Stub script: records its own name and each argv word to STUB_LOG, one item
# per line. Reads stdin and appends it prefixed with "STDIN:" so tests can
# verify the token was forwarded rather than lost.
_STUB = """\
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_NAME="$(basename "$0")"
LOG="${STUB_LOG:-/dev/null}"
printf '%s\\n' "$SCRIPT_NAME" "$@" >> "$LOG"
if [ -t 0 ]; then
    printf 'STDIN:<tty>\\n' >> "$LOG"
else
    IFS= read -r STDIN_LINE || true
    printf 'STDIN:%s\\n' "$STDIN_LINE" >> "$LOG"
fi
exit 0
"""


@pytest.fixture()
def runner_env(tmp_path):
    """Yield (env_dict, stub_log_path) with stubs installed in scripts_dir."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    stub_log = tmp_path / "stub.log"

    for name in ("provision.sh", "teardown.sh", "reap.sh"):
        stub = scripts_dir / name
        stub.write_text(_STUB)
        stub.chmod(0o755)

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "SCRIPTS_DIR": str(scripts_dir),
        "LOG_FILE": str(tmp_path / "forced-command.log"),
        "STUB_LOG": str(stub_log),
    }
    yield env, stub_log


def _run(env, ssh_cmd, stdin=b""):
    full_env = dict(env)
    if ssh_cmd is not None:
        full_env["SSH_ORIGINAL_COMMAND"] = ssh_cmd
    elif "SSH_ORIGINAL_COMMAND" in full_env:
        del full_env["SSH_ORIGINAL_COMMAND"]
    return subprocess.run(
        ["bash", str(DISPATCHER)],
        env=full_env,
        input=stdin,
        capture_output=True,
    )


def _stub_calls(stub_log: Path) -> list[list[str]]:
    """Parse stub_log into a list of [script_name, arg1, ...] per call."""
    if not stub_log.exists():
        return []
    lines = stub_log.read_text().splitlines()
    calls: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("STDIN:"):
            if current:
                current.append(line)
                calls.append(current)
                current = []
        else:
            if line in ("provision.sh", "teardown.sh", "reap.sh"):
                if current:
                    calls.append(current)
                current = [line]
            else:
                current.append(line)
    if current:
        calls.append(current)
    return calls


# ---------------------------------------------------------------------------
# Accepted invocations
# ---------------------------------------------------------------------------

def test_provision_accepted(runner_env):
    env, stub_log = runner_env
    result = _run(env, "provision.sh gh-runner-1 https://github.com/o/r",
                  stdin=b"mytoken\n")
    assert result.returncode == 0, result.stderr
    calls = _stub_calls(stub_log)
    assert len(calls) == 1
    script, label, repo_url, *rest = calls[0]
    assert script == "provision.sh"
    assert label == "gh-runner-1"
    assert repo_url == "https://github.com/o/r"
    # Token must NOT appear in any argv position.
    argv_str = " ".join(calls[0])
    assert "mytoken" not in argv_str or any(
        item.startswith("STDIN:") and "mytoken" in item for item in calls[0]
    ), "token leaked into argv"


def test_provision_token_forwarded_via_stdin(runner_env):
    """Token on stdin reaches the stub via stdin, not argv."""
    env, stub_log = runner_env
    _run(env, "provision.sh label-x https://github.com/org/repo",
         stdin=b"secret-token\n")
    calls = _stub_calls(stub_log)
    assert calls, "stub was not called"
    call = calls[0]
    # argv has no token
    argv_parts = [p for p in call if not p.startswith("STDIN:")]
    assert "secret-token" not in " ".join(argv_parts)
    # stdin line carries the token
    stdin_parts = [p for p in call if p.startswith("STDIN:")]
    assert any("secret-token" in p for p in stdin_parts), \
        "token not found in stub stdin"


def test_teardown_accepted(runner_env):
    env, stub_log = runner_env
    result = _run(env, "teardown.sh 1234")
    assert result.returncode == 0, result.stderr
    calls = _stub_calls(stub_log)
    assert len(calls) == 1
    assert calls[0][0] == "teardown.sh"
    assert calls[0][1] == "1234"


def test_reap_dry_run_accepted(runner_env):
    env, stub_log = runner_env
    result = _run(env, "reap.sh --dry-run")
    assert result.returncode == 0, result.stderr
    calls = _stub_calls(stub_log)
    assert len(calls) == 1
    assert calls[0][0] == "reap.sh"
    assert "--dry-run" in calls[0]


def test_reap_no_args_accepted(runner_env):
    env, stub_log = runner_env
    result = _run(env, "reap.sh")
    assert result.returncode == 0, result.stderr
    calls = _stub_calls(stub_log)
    assert len(calls) == 1
    assert calls[0][0] == "reap.sh"


def test_reap_max_age_accepted(runner_env):
    env, stub_log = runner_env
    result = _run(env, "reap.sh --max-age-hours 6")
    assert result.returncode == 0, result.stderr
    calls = _stub_calls(stub_log)
    assert calls[0][0] == "reap.sh"
    assert "--max-age-hours" in calls[0]
    assert "6" in calls[0]


# ---------------------------------------------------------------------------
# Refused invocations — stub must never be called
# ---------------------------------------------------------------------------

def _assert_refused(runner_env, ssh_cmd, *, stdin=b""):
    env, stub_log = runner_env
    result = _run(env, ssh_cmd, stdin=stdin)
    assert result.returncode != 0, \
        f"expected refusal for {ssh_cmd!r} but got exit 0"
    calls = _stub_calls(stub_log)
    assert calls == [], \
        f"stub was called despite refusal for {ssh_cmd!r}: {calls}"


def test_refuse_shell_injection_semicolon(runner_env):
    # "teardown.sh 1234; rm -rf /" — injection after semicolon must be refused
    # before any exec. Check that neither "rm" nor "rf" appear in stub argv.
    env, stub_log = runner_env
    result = _run(env, "teardown.sh 1234; rm -rf /")
    assert result.returncode != 0
    assert _stub_calls(stub_log) == [], "stub must not be called on injection attempt"


def test_refuse_subshell_injection(runner_env):
    # "teardown.sh $(cat /etc/shadow)" — command substitution in argv
    _assert_refused(runner_env, "teardown.sh $(cat /etc/shadow)")


def test_refuse_label_with_space(runner_env):
    # provision.sh "a b" ... → split into 3+ words → wrong arity
    _assert_refused(runner_env, 'provision.sh "a b" https://github.com/o/r')


def test_refuse_unknown_verb(runner_env):
    _assert_refused(runner_env, "qm destroy 101")


def test_refuse_empty_command(runner_env):
    env, stub_log = runner_env
    result = _run(env, "")
    assert result.returncode != 0
    assert _stub_calls(stub_log) == []


def test_refuse_missing_ssh_original_command(runner_env):
    env, stub_log = runner_env
    result = _run(env, None)  # SSH_ORIGINAL_COMMAND not set
    assert result.returncode != 0
    assert _stub_calls(stub_log) == []


def test_refuse_provision_extra_args(runner_env):
    # provision.sh 1234 --purge --extra → 3 args, wants 2
    _assert_refused(runner_env, "provision.sh 1234 --purge --extra")


def test_refuse_teardown_extra_args(runner_env):
    _assert_refused(runner_env, "teardown.sh 1234 --purge")


def test_refuse_teardown_non_numeric_vmid(runner_env):
    _assert_refused(runner_env, "teardown.sh abc123")


def test_refuse_provision_invalid_label_chars(runner_env):
    # Label with a shell-special character
    _assert_refused(runner_env, "provision.sh runner;bad https://github.com/o/r")


def test_refuse_provision_non_https_url(runner_env):
    _assert_refused(runner_env, "provision.sh label http://github.com/o/r")


def test_refuse_provision_non_github_url(runner_env):
    _assert_refused(runner_env, "provision.sh label https://evil.example.com/o/r")


def test_refuse_reap_unknown_flag(runner_env):
    _assert_refused(runner_env, "reap.sh --purge")


def test_refuse_reap_max_age_non_numeric(runner_env):
    _assert_refused(runner_env, "reap.sh --max-age-hours abc")


def test_refuse_reap_max_age_missing_value(runner_env):
    _assert_refused(runner_env, "reap.sh --max-age-hours")


# ---------------------------------------------------------------------------
# No offending content in stub argv on any refusal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ssh_cmd,offender", [
    ("teardown.sh 1234; rm -rf /", "rm"),
    ("teardown.sh $(cat /etc/shadow)", "shadow"),
    ('provision.sh "a b" https://github.com/o/r', "a b"),
    ("qm destroy 101", "qm"),
    ("provision.sh 1234 --purge --extra", "--purge"),
])
def test_offender_never_reaches_stub(runner_env, ssh_cmd, offender):
    """Refused commands must leave no trace of the offending word in stub argv."""
    env, stub_log = runner_env
    _run(env, ssh_cmd)
    raw = stub_log.read_text() if stub_log.exists() else ""
    assert offender not in raw, \
        f"offender {offender!r} found in stub log for command {ssh_cmd!r}"
