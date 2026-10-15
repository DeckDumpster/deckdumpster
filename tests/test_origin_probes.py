"""Every probe of a running instance resolves the listener its mode serves (sp-8lil3y).

Multi-tenant serves no 8081: its listener is plain HTTP on container 8080 and it
answers 401 outside /health. deploy.sh, cdn-check, handles.sh and the serving
check each hard-coded one side of that. These drive the real scripts with podman
and curl stubbed: curl answers only the URL the container would really serve.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy"

PODMAN_STUB = """#!/usr/bin/env bash
[ -n "$CONTAINER_DOWN" ] && exit 0
case "$1" in
    port)
        case "$3" in
            8081/tcp) [ "$MODE" = single ] && echo "0.0.0.0:8083" ;;
            8080/tcp) [ "$MODE" = multitenant ] && echo "127.0.0.1:8091" ;;
        esac ;;
esac
exit 0
"""
# Multi-tenant: /health 200, everything else 401. Single: everything 200 over TLS.
CURL_STUB = """#!/usr/bin/env bash
for a in "$@"; do url="$a"; done
printf '%s\\n' "$url" >> "$CURL_CALL_LOG"
if [ "$MODE" = multitenant ]; then
    case "$url" in
        http://127.0.0.1:8091/health) code=200 ;;
        http://127.0.0.1:8091/*) code=401 ;;
        *) exit 7 ;;
    esac
else
    case "$url" in https://127.0.0.1:8083/*) code=200 ;; *) exit 7 ;; esac
fi
case "$*" in
    *-w*) printf '%s' "$code" ;;
    *-D*) printf 'HTTP/1.1 %s X\\r\\n\\r\\n' "$code" ;;
esac
exit 0
"""


def _run(tmp_path, script, mode, *, down=False, args=()):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("podman", PODMAN_STUB), ("curl", CURL_STUB)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MODE=mode,
               CURL_CALL_LOG=str(tmp_path / "curl.log"), MTGC_INSTANCE="prod")
    env.pop("MTGC_ORIGIN_URL", None)
    if down:
        env["CONTAINER_DOWN"] = "1"
    return subprocess.run(
        ["bash", str(DEPLOY_DIR / script), *args], capture_output=True, text=True,
        env=env, cwd=tmp_path, timeout=DEFAULT_TIMEOUT,
    )


@pytest.mark.parametrize("mode", ["multitenant", "single"])
def test_serving_check_passes_when_the_modes_listener_answers(tmp_path, mode):
    r = _run(tmp_path, "serving-check.sh", mode, args=["prod"])
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("mode", ["multitenant", "single"])
def test_serving_check_fails_with_the_container_down(tmp_path, mode):
    r = _run(tmp_path, "serving-check.sh", mode, down=True, args=["prod"])
    assert r.returncode == 1, r.stdout + r.stderr


def test_cdn_check_origin_probe_accepts_the_multitenant_challenge(tmp_path):
    # Fails after the origin step (the edge is the stub's "exit 7"); what matters
    # is that it got past the origin and says nothing about it.
    r = _run(tmp_path, "cdn-check.sh", "multitenant")
    assert "origin" not in r.stderr.split("FAILED")[-1].split("\n")[0].lower(), r.stderr
    assert "http://127.0.0.1:8091/" in (tmp_path / "curl.log").read_text()


def test_cdn_check_fails_with_the_container_down(tmp_path):
    r = _run(tmp_path, "cdn-check.sh", "multitenant", down=True)
    assert r.returncode == 1
    assert "no running origin" in r.stderr


# --- the literal-port ratchet -------------------------------------------------
# Setup paths create single-tenant instances and may name 8081. A script that
# PROBES a running instance may not. Default-deny: every deploy/*.sh and workflow
# is scanned, and the exemptions are the files that only set instances up.
SETUP_ONLY = {
    "ci.sh", "setup.sh", "mac-setup.sh", "mac-deploy.sh", "mac-teardown.sh",
    "render-quadlet.sh", "origin-lib.sh",
}
PROBE_8081 = re.compile(r"(localhost|127\.0\.0\.1):8081|port[^\n]*\b8081/tcp|8081/tcp[^\n]*port")


def probes_naming_8081(text):
    return [ln for ln in text.splitlines()
            if not ln.lstrip().startswith("#") and PROBE_8081.search(ln)]


def test_no_probe_of_a_running_instance_names_8081():
    offenders = {}
    files = [p for p in DEPLOY_DIR.glob("*") if p.is_file() and p.name not in SETUP_ONLY
             and p.suffix in {".sh", ".service"}]
    files += list((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    for p in files:
        bad = probes_naming_8081(p.read_text())
        if bad:
            offenders[str(p.relative_to(REPO_ROOT))] = bad
    assert not offenders, offenders


def test_the_ratchet_flags_a_planted_probe():
    assert probes_naming_8081("curl -sSfk https://localhost:8081/")
    assert probes_naming_8081('PORT=$(podman port systemd-mtgc-prod 8081/tcp)')
    assert not probes_naming_8081("# https://localhost:8081/ is single-tenant")
