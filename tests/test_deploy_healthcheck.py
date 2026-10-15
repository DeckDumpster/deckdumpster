"""deploy.sh's health check probes the listener the running mode serves (sp-iqgac5).

Multi-tenant mode serves only the plain-HTTP 8080 listener ("port 8081 is not
served"), so a check on 8081 reported every healthy deploy as failed. These drive
the real deploy.sh with podman, systemctl and curl stubbed: curl answers only for
the one URL the container would really serve.
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy" / "deploy.sh"

# 8081 is published (to 8083) in both modes; 8080 only when MTGC_HTTP_PORT is.
PODMAN_STUB = """#!/usr/bin/env bash
case "$1" in
    --version) echo "podman version 0.0.0-stub" ;;
    port)
        case "$3" in
            8081/tcp) echo "0.0.0.0:8083" ;;
            8080/tcp) [ -n "$PUBLISH_8080" ] && echo "127.0.0.1:8091" ;;
        esac ;;
esac
exit 0
"""
NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
# Healthy only at $SERVES; anything else (a stopped container) is refused.
CURL_STUB = """#!/usr/bin/env bash
for a in "$@"; do url="$a"; done
[ "$url" = "$SERVES" ]
"""


@pytest.fixture
def run_deploy(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", NOOP_STUB),
        ("loginctl", NOOP_STUB),
        ("sleep", NOOP_STUB),
        ("curl", CURL_STUB),
    ):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    home = tmp_path / "home"
    (home / ".config/containers/systemd").mkdir(parents=True)
    (home / ".config/containers/systemd/mtgc-prod.container").write_text("")

    def run(serves, publish_8080):
        env = dict(os.environ)
        env.update(
            HOME=str(home),
            PATH=f"{bin_dir}:{env['PATH']}",
            XDG_RUNTIME_DIR=str(tmp_path / "run"),
            MTGC_DISK_FLOOR_GB="0",
            MTGC_STORE_ROOT=str(tmp_path / "store"),
            MTGC_FREEZE_DIR=str(tmp_path / "freeze"),
            SERVES=serves,
        )
        if publish_8080:
            env["PUBLISH_8080"] = "1"
        return subprocess.run(
            ["bash", str(DEPLOY), "prod"], capture_output=True, text=True,
            env=env, cwd=str(REPO_ROOT), timeout=DEFAULT_TIMEOUT,
        )

    return run


def test_multitenant_container_serving_8080_passes(run_deploy):
    r = run_deploy("http://localhost:8091/", publish_8080=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Health check passed" in r.stdout


def test_multitenant_stopped_container_fails(run_deploy):
    r = run_deploy("", publish_8080=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Health check FAILED" in r.stdout, r.stdout + r.stderr


def test_single_tenant_still_probes_8081_over_tls(run_deploy):
    r = run_deploy("https://localhost:8083/", publish_8080=False)
    assert r.returncode == 0, r.stdout + r.stderr
