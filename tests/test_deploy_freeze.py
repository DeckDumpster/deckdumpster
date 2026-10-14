"""A production cutover can freeze deploys; deploy.sh must honour it (sp-4vlkdc).

2026-10-14: a merge during the multi-tenancy cutover ran `deploy.sh prod`, which
restarted mtgc-prod mid-migration. These drive the real deploy.sh with podman and
systemctl stubbed, and assert the unit is never restarted while a marker exists.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy" / "deploy.sh"
FREEZE = REPO_ROOT / "deploy" / "freeze.sh"

PODMAN_STUB = """#!/usr/bin/env bash
case "$1" in
    --version) echo "podman version 0.0.0-stub" ;;
    port) echo "0.0.0.0:8083" ;;
esac
exit 0
"""
NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
SYSTEMCTL_STUB = '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$SYSTEMCTL_LOG"\nexit 0\n'
CURL_STUB = '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$CURL_LOG"\nexit 0\n'


@pytest.fixture
def host(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", SYSTEMCTL_STUB),
        ("loginctl", NOOP_STUB),
        ("curl", CURL_STUB),
    ):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    home = tmp_path / "home"
    (home / ".config/containers/systemd").mkdir(parents=True)
    # An existing instance: the Quadlet is there, so deploy.sh takes the
    # rebuild-and-restart path.
    (home / ".config/containers/systemd/mtgc-prod.container").write_text("")
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{env['PATH']}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        SYSTEMCTL_LOG=str(tmp_path / "systemctl.log"),
        CURL_LOG=str(tmp_path / "curl.log"),
        MTGC_DISK_FLOOR_GB="0",
        MTGC_STORE_ROOT=str(tmp_path / "store"),
        MTGC_FREEZE_DIR=str(tmp_path / "freeze"),
        PUSHOVER_TOKEN="t",
        PUSHOVER_USER="u",
        PUSHOVER_API_URL="https://pushover.example/m.json",
    )

    class Host:
        def __init__(self):
            self.env = env
            self.systemctl_log = tmp_path / "systemctl.log"
            self.curl_log = tmp_path / "curl.log"
            self.marker = tmp_path / "freeze" / "freeze-prod"

        def run(self, script, *args):
            return subprocess.run(
                ["bash", str(script), *args],
                capture_output=True, text=True, env=env,
                cwd=str(REPO_ROOT), timeout=DEFAULT_TIMEOUT,
            )

        def restarts(self):
            if not self.systemctl_log.exists():
                return []
            return [c for c in self.systemctl_log.read_text().splitlines() if " restart " in f" {c} "]

    return Host()


def freeze(host, until):
    r = host.run(FREEZE, "set", "prod", "--holder", "concierge",
                 "--reason", "tenant cutover", "--until", str(until))
    assert r.returncode == 0, r.stderr


def test_deploy_without_marker_restarts_as_before(host):
    r = host.run(DEPLOY, "prod")
    assert r.returncode == 0, r.stdout + r.stderr
    assert host.restarts() == ["--user restart mtgc-prod"]


def test_deploy_with_marker_refuses_and_does_not_restart(host):
    freeze(host, int(time.time()) + 3600)
    r = host.run(DEPLOY, "prod")
    assert r.returncode != 0
    assert "DEPLOY FROZEN" in r.stderr
    assert "concierge" in r.stderr and "tenant cutover" in r.stderr
    assert host.restarts() == []


def test_clearing_the_marker_lets_deploy_proceed(host):
    freeze(host, int(time.time()) + 3600)
    assert host.run(FREEZE, "clear", "prod").returncode == 0
    assert host.run(DEPLOY, "prod").returncode == 0
    assert host.restarts() == ["--user restart mtgc-prod"]


def test_stale_marker_still_blocks_and_alarms(host):
    freeze(host, int(time.time()) - 10)
    r = host.run(DEPLOY, "prod")
    assert r.returncode != 0 and host.restarts() == []
    alarm = host.run(FREEZE, "alarm", "prod")
    assert alarm.returncode == 1
    assert "overdue" in host.curl_log.read_text()


def test_alarm_is_quiet_within_the_window_and_without_a_marker(host):
    assert host.run(FREEZE, "alarm", "prod").returncode == 0
    freeze(host, int(time.time()) + 3600)
    assert host.run(FREEZE, "alarm", "prod").returncode == 0
    assert not host.curl_log.exists()


def test_a_second_freeze_does_not_overwrite_the_first(host):
    freeze(host, int(time.time()) + 3600)
    r = host.run(FREEZE, "set", "prod", "--holder", "x", "--reason", "y",
                 "--until", str(int(time.time()) + 60))
    assert r.returncode != 0
    assert "concierge" in host.marker.read_text()
