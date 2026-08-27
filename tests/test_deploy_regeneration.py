"""Regenerating a missing Quadlet must reproduce the unit it replaces.

`deploy.sh` regenerates a missing Quadlet by calling `setup.sh <instance>` with
no flags. `--http-port` and `--tls-certs` are inputs to the render, so unless
they are recorded somewhere the regenerated unit silently loses the plaintext
publish and the certificate mount.

These tests drive the real `setup.sh` with podman/systemd/loginctl stubbed out,
so they exercise the same code path `deploy.sh` triggers.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP = REPO_ROOT / "deploy" / "setup.sh"
DEPLOY = REPO_ROOT / "deploy" / "deploy.sh"

# `podman volume exists` must fail so setup.sh does not splice in the shared
# reference volume; everything else is a no-op that reports success.
PODMAN_STUB = """#!/usr/bin/env bash
case "$1" in
    volume) exit 1 ;;
    --version) echo "podman version 0.0.0-stub" ;;
esac
exit 0
"""

NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"

LINGER_STUB = "#!/usr/bin/env bash\necho 'Linger=yes'\nexit 0\n"


@pytest.fixture
def host(tmp_path):
    """A fake host: stubbed podman/systemctl/loginctl and an empty $HOME."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", NOOP_STUB),
        ("loginctl", LINGER_STUB),
    ):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["XDG_RUNTIME_DIR"] = str(tmp_path / "run")
    # The floor gate (de-yef) measures the filesystem the run will write to,
    # which under a tmp_path $HOME is pytest's scratch disk, not the deploy box's.
    # Unpinned, every test here passes or fails on how full /tmp happens to be —
    # 35 of them went red on a box whose /tmp sat at 92%. Zero is the documented
    # knob (there is no bypass flag); what the floor does with a real number is
    # tests/test_diskcheck.py's subject, not this file's.
    env["MTGC_DISK_FLOOR_GB"] = "0"

    class Host:
        def __init__(self):
            self.home = home
            self.env = env

        def setup(self, *args):
            result = subprocess.run(
                ["bash", str(SETUP), *args],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(REPO_ROOT),
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result

        def quadlet(self, instance):
            return (
                home
                / ".config/containers/systemd"
                / f"mtgc-{instance}.container"
            )

        def env_file(self, instance):
            return home / ".config/mtgc" / f"{instance}.env"

    return Host()


def test_regenerating_a_missing_quadlet_keeps_the_http_publish(host):
    """The exact sequence deploy.sh performs when the unit has gone missing."""
    host.setup("inst", "8083", "--http-port", "8084")
    unit = host.quadlet("inst")
    assert "PublishPort=127.0.0.1:8084:8080" in unit.read_text()

    unit.unlink()
    host.setup("inst")  # deploy.sh regenerates with no flags

    assert "PublishPort=127.0.0.1:8084:8080" in unit.read_text()


def test_regenerating_a_missing_quadlet_keeps_the_cert_mount(host):
    certs = host.home / "certs"
    certs.mkdir()
    host.setup("inst", "8083", "--tls-certs", str(certs))
    unit = host.quadlet("inst")
    assert f"Volume={certs}:/certs:ro,Z" in unit.read_text()

    unit.unlink()
    host.setup("inst")

    assert f"Volume={certs}:/certs:ro,Z" in unit.read_text()


def test_regeneration_reproduces_both_flags_together(host):
    """Both flag-derived lines come back, and nothing else the render owns
    changes. The explicit HTTPS host port is the one input still not recorded —
    a pre-existing gap tracked separately as de-f2d, so this compares the unit
    with the PublishPort=<host>:8081 line excluded rather than whole-file."""
    certs = host.home / "certs"
    certs.mkdir()
    host.setup("inst", "8083", "--http-port", "8084", "--tls-certs", str(certs))
    unit = host.quadlet("inst")

    def without_https_publish(text):
        return [ln for ln in text.splitlines() if not ln.endswith(":8081")]

    original = without_https_publish(unit.read_text())

    unit.unlink()
    host.setup("inst")

    regenerated = unit.read_text()
    assert without_https_publish(regenerated) == original
    assert "PublishPort=127.0.0.1:8084:8080" in regenerated
    assert f"Volume={certs}:/certs:ro,Z" in regenerated


def test_an_explicit_flag_overrides_the_recorded_value(host):
    host.setup("inst", "8083", "--http-port", "8084")
    host.setup("inst", "8083", "--http-port", "8085")

    unit = host.quadlet("inst").read_text()
    assert "PublishPort=127.0.0.1:8085:8080" in unit
    assert "8084" not in unit


def test_deleting_the_recorded_line_drops_the_setting(host):
    """No --no-http-port flag: removal is an env-file edit, as documented."""
    host.setup("inst", "8083", "--http-port", "8084")
    env_file = host.env_file("inst")
    env_file.write_text(
        "".join(
            line
            for line in env_file.read_text().splitlines(keepends=True)
            if not line.startswith("MTGC_HTTP_PUBLISH_PORT=")
        )
    )

    host.setup("inst", "8083")

    assert "8084" not in host.quadlet("inst").read_text()


def test_unset_flags_record_nothing_and_render_unchanged(host):
    """UNSET MEANS UNCHANGED: an instance created without the flags must gain
    neither a recorded setting nor a line in the generated unit."""
    host.setup("inst", "8083")

    env_text = host.env_file("inst").read_text()
    assert "MTGC_HTTP_PUBLISH_PORT" not in env_text
    assert "MTGC_TLS_CERTS_DIR" not in env_text

    unit = host.quadlet("inst").read_text()
    assert unit.count("PublishPort=") == 1
    assert "/certs" not in unit


def test_recording_leaves_the_rest_of_the_env_file_alone(host):
    host.setup("inst", "8083")
    env_file = host.env_file("inst")
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-secret\nMTGC_TLS_CERT=/certs/c.pem\n")

    host.setup("inst", "8083", "--http-port", "8084")

    lines = env_file.read_text().splitlines()
    assert "ANTHROPIC_API_KEY=sk-ant-secret" in lines
    assert "MTGC_TLS_CERT=/certs/c.pem" in lines
    assert "MTGC_HTTP_PUBLISH_PORT=8084" in lines


def test_env_file_stays_private_after_recording(host):
    """It holds the API key — recording must not widen its mode."""
    host.setup("inst", "8083", "--http-port", "8084")
    mode = host.env_file("inst").stat().st_mode & 0o777
    assert mode == 0o600


def test_a_recorded_cert_dir_that_vanished_fails_loudly(host):
    """No fallback: regenerating against a missing cert directory must not
    quietly render a unit without the mount."""
    certs = host.home / "certs"
    certs.mkdir()
    host.setup("inst", "8083", "--tls-certs", str(certs))
    certs.rmdir()

    result = subprocess.run(
        ["bash", str(SETUP), "inst"],
        capture_output=True,
        text=True,
        env=host.env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode != 0
    assert "--tls-certs directory does not exist" in result.stdout + result.stderr


def test_deploy_regenerates_through_setup(host):
    """deploy.sh delegates the missing-unit case to setup.sh with only the
    instance name — which is safe precisely because setup.sh reloads the
    recorded flags."""
    text = DEPLOY.read_text()
    assert 'bash "$SCRIPT_DIR/setup.sh" "$INSTANCE"' in text
