"""deploy.sh converges an existing Quadlet to the checkout's render (sp-ymom8y).

prod's installed unit predated the oidc.env line in deploy/mtgc.container and
every deploy reported success. These drive the real deploy.sh with podman and
systemctl stubbed; the floor is unreachable so a run that gets past the converge
stops at diskcheck, before any build.
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy" / "deploy.sh"
SETUP = REPO_ROOT / "deploy" / "setup.sh"

PODMAN_STUB = '#!/usr/bin/env bash\ncase "$1" in volume) exit 1 ;; esac\nexit 0\n'
NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
SYSTEMCTL_STUB = '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$SYSTEMCTL_LOG"\nexit 0\n'


@pytest.fixture
def host(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", SYSTEMCTL_STUB),
        ("loginctl", "#!/usr/bin/env bash\necho Linger=yes\n"),
    ):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PATH=f"{bin_dir}:{env['PATH']}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        SYSTEMCTL_LOG=str(tmp_path / "systemctl.log"),
        MTGC_DISK_FLOOR_GB="0",
        MTGC_FREEZE_DIR=str(tmp_path / "freeze"),
    )

    class Host:
        unit = home / ".config/containers/systemd/mtgc-prod.container"

        def run(self, script, *args):
            return subprocess.run(
                ["bash", str(script), *args], capture_output=True, text=True,
                env=env, cwd=str(REPO_ROOT), timeout=DEFAULT_TIMEOUT,
            )

        def deploy(self):
            # Unreachable floor: stops at diskcheck, after the converge.
            env["MTGC_DISK_FLOOR_GB"] = "999999999"
            return self.run(DEPLOY, "prod")

        def baks(self):
            return list(self.unit.parent.glob("mtgc-prod.container.*.bak"))

    h = Host()
    r = h.run(SETUP, "prod", "8081", "--http-port", "8091")
    assert r.returncode == 0, r.stdout + r.stderr
    return h


def test_stale_quadlet_missing_a_template_line_is_rewritten(host):
    current = host.unit.read_text()
    stale = "\n".join(
        line for line in current.splitlines() if "oidc.env" not in line
    ) + "\n"
    host.unit.write_text(stale)

    r = host.deploy()

    assert "oidc.env" in host.unit.read_text()
    assert host.unit.read_text() == current
    assert len(host.baks()) == 1 and host.baks()[0].read_text() == stale
    assert "oidc.env" in r.stdout  # the diff was printed


def test_converged_quadlet_is_left_alone(host):
    before = host.unit.read_text()
    host.deploy()
    assert host.unit.read_text() == before
    assert host.baks() == []


def test_hand_added_port_is_refused_with_the_diff(host):
    drifted = host.unit.read_text().replace(
        "PublishPort=127.0.0.1:8091:8080",
        "PublishPort=127.0.0.1:8091:8080\nPublishPort=127.0.0.1:9999:8080",
    )
    host.unit.write_text(drifted)

    r = host.deploy()

    assert r.returncode != 0
    assert "CONVERGE REFUSED" in r.stderr and "9999" in r.stderr
    assert "9999" in r.stdout  # the diff
    assert host.unit.read_text() == drifted
    assert host.baks() == []


def test_prod_without_a_recorded_https_port_still_converges_on_8081(host):
    """The installed prod unit publishes 8081:8081 with no MTGC_PUBLISH_PORT
    recorded; the render must reproduce it, not ':8081' (sp-972mdc)."""
    env_file = host.unit.parents[2] / "mtgc" / "prod.env"
    kept = [
        line for line in env_file.read_text().splitlines()
        if not line.startswith("MTGC_PUBLISH_PORT=")
    ]
    env_file.write_text("\n".join(kept) + "\n")
    before = host.unit.read_text()
    assert "PublishPort=8081:8081" in before

    r = host.deploy()

    assert "CONVERGE REFUSED" not in r.stderr, r.stderr
    assert host.unit.read_text() == before
    assert "PublishPort=127.0.0.1:8091:8080" in before
