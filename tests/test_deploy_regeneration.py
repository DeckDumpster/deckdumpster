"""Regenerating a missing Quadlet must reproduce the unit it replaces.

`deploy.sh` regenerates a missing Quadlet by calling `setup.sh <instance>` with
nothing but the instance name. `--http-port`, `--tls-certs` and the positional
port are inputs to the render, so unless they are recorded somewhere the
regenerated unit silently loses the plaintext publish, the certificate mount and
the pinned HTTPS host port.

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
    # 41 of them went red on a box whose /tmp sat at 92%. Zero is the documented
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


def test_regeneration_reproduces_the_whole_unit(host):
    """Every input the render owns comes back — byte-for-byte, not line by line.
    Whole-file identity is the assertion that catches the next input someone
    adds without recording it."""
    certs = host.home / "certs"
    certs.mkdir()
    host.setup("inst", "8083", "--http-port", "8084", "--tls-certs", str(certs))
    unit = host.quadlet("inst")
    original = unit.read_text()

    unit.unlink()
    host.setup("inst")

    assert unit.read_text() == original
    assert "PublishPort=8083:8081" in original
    assert "PublishPort=127.0.0.1:8084:8080" in original
    assert f"Volume={certs}:/certs:ro,Z" in original


def test_regenerating_a_missing_quadlet_keeps_the_https_port(host):
    """de-f2d: an instance created on an explicit port must come back on it.
    The old failure was silent — deploy.sh discovers the port from `podman
    port`, so its health check passes on whatever high port Podman picked."""
    host.setup("inst", "8083")
    unit = host.quadlet("inst")
    assert "PublishPort=8083:8081" in unit.read_text()

    unit.unlink()
    host.setup("inst")  # deploy.sh regenerates with no port

    assert "PublishPort=8083:8081" in unit.read_text()


def test_an_explicit_port_overrides_the_recorded_one(host):
    host.setup("inst", "8083")
    host.setup("inst", "8085")

    unit = host.quadlet("inst").read_text()
    assert "PublishPort=8085:8081" in unit
    assert "8083" not in unit


def test_an_auto_assigned_port_records_nothing(host):
    """Auto-assign is the absence of a port, not a port: recording 0 — or
    whatever Podman happened to pick — would pin an instance that asked to
    float."""
    host.setup("inst")

    assert "MTGC_PUBLISH_PORT" not in host.env_file("inst").read_text()
    assert "PublishPort=:8081" in host.quadlet("inst").read_text()

    host.quadlet("inst").unlink()
    host.setup("inst")

    assert "PublishPort=:8081" in host.quadlet("inst").read_text()


def test_deleting_the_recorded_port_returns_the_instance_to_auto_assign(host):
    """Same removal mechanism as the two flags: there is no --no-port."""
    host.setup("inst", "8083")
    env_file = host.env_file("inst")
    env_file.write_text(
        "".join(
            line
            for line in env_file.read_text().splitlines(keepends=True)
            if not line.startswith("MTGC_PUBLISH_PORT=")
        )
    )

    host.setup("inst")

    assert "PublishPort=:8081" in host.quadlet("inst").read_text()


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
    assert "MTGC_PUBLISH_PORT=8083" in env_text  # the port WAS given explicitly

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
    assert "MTGC_PUBLISH_PORT=8083" in lines


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


# --- Memory ceiling (de-4u8g) ------------------------------------------------
#
# On 2026-08-27 the CI runner was OOM-killed with ~10 polecats in flight. It
# does not auto-restart, so CI was dead ~24 h: 24 PRs queued checks that never
# ran and main froze. The runner unit is hardened separately, and that limit
# does not reach these containers — each instance is its own
# mtgc-<instance>.service with its own cgroup, generated from
# deploy/mtgc.container.


def test_an_ephemeral_instance_is_generated_with_a_ceiling(host):
    """The whole point: an instance that cannot take the box with it."""
    host.setup("inst", "8083")

    unit = host.quadlet("inst").read_text()
    assert "MemoryMax=2G" in unit


def test_prod_is_generated_without_any_memory_directive(host):
    """THE PROD EXCLUSION, by name — the same shape as the store.env exception
    (de-oqu, tests/test_deploy_store.py). Prod's working set is not something
    this repo gets to guess at, and an OOM kill there is an outage rather than a
    failed test. NO Memory* directive at all, not a generous one."""
    host.setup("prod", "8081")

    unit = host.quadlet("prod").read_text()
    assert "Memory" not in unit
    assert "{{MEMORY_LIMIT}}" not in unit


def test_regenerating_a_missing_quadlet_keeps_the_ceiling(host):
    """The ceiling is derived from the instance name, not from a recorded flag,
    so the regeneration deploy.sh performs cannot drop it."""
    host.setup("inst", "8083")
    unit = host.quadlet("inst")
    unit.unlink()

    host.setup("inst")  # deploy.sh regenerates with no flags

    assert "MemoryMax=2G" in unit.read_text()


def test_the_ceiling_is_not_recorded_in_the_env_file(host):
    """It is not an operator setting, so there is nothing to go stale: a box
    that edits the constant gets the new value on the next setup.sh run."""
    host.setup("inst", "8083")

    assert "Memory" not in host.env_file("inst").read_text()
