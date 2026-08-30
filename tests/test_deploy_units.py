"""A unit added to the repo has to reach a host that already exists.

`deploy.sh` runs `setup.sh` only when an instance's Quadlet is *missing*, so
for an instance that is already installed — prod — the redeploy path is the
only route a newly added timer unit can travel. It did not travel it: prod ran
for months with `mtgc-catalog-check`, `mtgc-catalog-refresh` and
`mtgc-diskcheck` absent from the host entirely, each one a feature that had
landed on main and deployed (de-46k).

These drive the real scripts with podman/systemd/loginctl stubbed out, the same
way tests/test_deploy_regeneration.py does.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP = REPO_ROOT / "deploy" / "setup.sh"
DEPLOY = REPO_ROOT / "deploy" / "deploy.sh"
TEARDOWN = REPO_ROOT / "deploy" / "teardown.sh"
PRUNE = REPO_ROOT / "deploy" / "prune-instances.sh"
UNITS_LIB = REPO_ROOT / "deploy" / "units-lib.sh"

# `podman volume exists` must fail so setup.sh does not splice in the shared
# reference volume. `podman port` has to answer, and curl has to succeed,
# because deploy.sh ends in port discovery and a health check against a
# container that does not exist here.
PODMAN_STUB = """#!/usr/bin/env bash
case "$1" in
    volume) exit 1 ;;
    --version) echo "podman version 0.0.0-stub" ;;
    port) echo "0.0.0.0:8083" ;;
esac
exit 0
"""

NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
LINGER_STUB = "#!/usr/bin/env bash\necho 'Linger=yes'\nexit 0\n"

# Records what the scripts ask systemd to do, so a test can assert on the verb
# rather than on the text of the script that would have produced it.
SYSTEMCTL_STUB = '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$SYSTEMCTL_LOG"\nexit 0\n'



@pytest.fixture
def host(tmp_path):
    """A fake host: stubbed podman/systemctl/loginctl and an empty $HOME."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("podman", PODMAN_STUB),
        ("systemctl", SYSTEMCTL_STUB),
        ("loginctl", LINGER_STUB),
        ("curl", NOOP_STUB),
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
    env["SYSTEMCTL_LOG"] = str(tmp_path / "systemctl.log")
    # setup.sh gates on free space before it would write a gigabyte of image
    # layers (de-yef). These tests stub podman and write a handful of unit
    # files, and pytest's tmp_path is on /tmp, which is not the disk the gate
    # exists to protect — so use the documented knob rather than letting a full
    # /tmp fail the suite for a reason the suite is not about.
    env["MTGC_DISK_FLOOR_GB"] = "0"

    class Host:
        def __init__(self):
            self.home = home
            self.env = env
            self.units_dir = home / ".config/systemd/user"
            self.systemctl_log = tmp_path / "systemctl.log"

        def systemctl_calls(self):
            if not self.systemctl_log.exists():
                return []
            return self.systemctl_log.read_text().splitlines()

        def run(self, script, *args, check=True):
            result = subprocess.run(
                ["bash", str(script), *args],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(REPO_ROOT),
            )
            if check:
                assert result.returncode == 0, result.stdout + result.stderr
            return result

        def setup(self, *args):
            return self.run(SETUP, *args)

        def deploy(self, *args):
            return self.run(DEPLOY, *args)

        def teardown(self, *args):
            return self.run(TEARDOWN, *args)

        def prune(self, *args):
            return self.run(PRUNE, *args)

        def write_units(self, instance, *prefixes):
            self.units_dir.mkdir(parents=True, exist_ok=True)
            for prefix in prefixes:
                for ext in ("service", "timer"):
                    (self.units_dir / f"{prefix}-{instance}.{ext}").write_text("")

        def installed(self, instance):
            if not self.units_dir.is_dir():
                return set()
            return {
                p.name[: -len(f"-{instance}.timer")]
                for p in self.units_dir.glob(f"mtgc-*-{instance}.timer")
            }

    return Host()


def repo_timer_prefixes():
    """Every timer template this repo defines — the expected install set."""
    return {p.name[: -len(".timer")] for p in (REPO_ROOT / "deploy").glob("mtgc-*.timer")}


def test_every_timer_template_has_a_service():
    """A .timer with no .service installs a pair that cannot start."""
    for prefix in repo_timer_prefixes():
        assert (REPO_ROOT / "deploy" / f"{prefix}.service").is_file(), prefix


def test_setup_installs_every_timer_the_repo_defines(host):
    host.setup("inst", "8083")
    assert host.installed("inst") == repo_timer_prefixes()


def test_redeploy_installs_a_unit_added_after_the_instance_existed(host):
    """The bug: prod's Quadlet exists, so deploy.sh skips setup.sh, so units
    the repo gained after install never reached the host."""
    host.setup("inst", "8083")

    # An instance installed before three of today's timers existed.
    for prefix in ("mtgc-catalog-check", "mtgc-catalog-refresh", "mtgc-diskcheck"):
        for ext in ("service", "timer"):
            (host.units_dir / f"{prefix}-inst.{ext}").unlink()
    assert host.installed("inst") != repo_timer_prefixes()

    host.deploy("inst")

    assert host.installed("inst") == repo_timer_prefixes()


def test_redeploy_does_not_go_through_setup(host):
    """Guards the reason this needed fixing at all: with the Quadlet present,
    deploy.sh never calls setup.sh, so installing units there is not
    redundant."""
    host.setup("inst", "8083")
    quadlet = host.home / ".config/containers/systemd/mtgc-inst.container"
    before = quadlet.read_text()

    result = host.deploy("inst")

    assert "running initial setup" not in result.stdout
    assert quadlet.read_text() == before


def test_reinstalling_rewrites_units_byte_identically(host):
    """Idempotence is what makes the redeploy install safe to do every time."""
    host.setup("inst", "8083")
    before = {p.name: p.read_text() for p in host.units_dir.iterdir()}

    host.deploy("inst")

    after = {p.name: p.read_text() for p in host.units_dir.iterdir()}
    assert after == before


def test_reinstalling_never_enables_a_timer(host):
    """Installing is not arming. Enable state lives in *.target.wants symlinks;
    a redeploy that armed prod's timers would be a production change nobody
    asked for."""
    host.setup("inst", "8083")
    host.systemctl_log.unlink(missing_ok=True)

    host.deploy("inst")

    for call in host.systemctl_calls():
        assert "enable" not in call, call
        assert not call.endswith(".timer"), call


def test_teardown_removes_a_unit_the_repo_no_longer_defines(host):
    """Removal reads the host, not the repo — otherwise a deleted template
    leaves its unit behind, armed and firing for an instance that is gone."""
    host.setup("inst", "8083")
    orphan = host.units_dir / "mtgc-retired-inst.timer"
    orphan.write_text("[Timer]\n")
    (host.units_dir / "mtgc-retired-inst.service").write_text("[Service]\n")

    host.teardown("inst")

    assert host.installed("inst") == set()
    assert not orphan.exists()


def test_teardown_with_no_units_left_to_remove_still_succeeds(host):
    """mtgc_units_installed returns nothing rather than failing, and the loop
    must not act on the empty line that leaves behind."""
    host.setup("inst", "8083")
    for unit in host.units_dir.glob("mtgc-*-inst.*"):
        unit.unlink()

    host.teardown("inst")

    assert host.installed("inst") == set()


def test_units_list_rejects_a_timer_with_no_service(tmp_path, host):
    """No fallback: a half-defined pair is an error, not a silent skip."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "deploy").mkdir(parents=True)
    (fake_repo / "deploy" / "mtgc-broken.timer").write_text("[Timer]\n")

    result = subprocess.run(
        ["bash", "-c", f'. "{UNITS_LIB}"; mtgc_units_list "{fake_repo}"'],
        capture_output=True,
        text=True,
        env=host.env,
    )
    assert result.returncode != 0
    assert "no matching" in result.stderr


def test_prune_reads_one_instance_off_overlapping_unit_names(host):
    """`mtgc-backup` and `mtgc-backup-check` are both real units, so a
    shortest-prefix match reads `mtgc-backup-check-ghost` as an instance called
    `check-ghost` and reports an orphan that never existed."""
    host.write_units("ghost", "mtgc-backup", "mtgc-backup-check", "mtgc-prices")

    result = host.prune("--dry-run")

    orphans = [
        line.strip("  - ")
        for line in result.stdout.splitlines()
        if line.startswith("  - ")
    ]
    assert orphans == ["ghost"]


def test_prune_removes_every_timer_the_host_has(host):
    """Not just the handful a role list happened to name — an orphan's leftover
    timer stays armed and keeps firing against a container that is gone."""
    host.write_units(
        "ghost",
        "mtgc-prices",
        "mtgc-backup",
        "mtgc-backup-check",
        "mtgc-catalog-check",
        "mtgc-catalog-refresh",
        "mtgc-diskcheck",
        "mtgc-edhrec",
        "mtgc-sealed-catalog",
    )
    (host.units_dir / "mtgc-alert-ghost@.service").write_text("")

    host.prune()

    assert host.installed("ghost") == set()
    assert not (host.units_dir / "mtgc-alert-ghost@.service").exists()
