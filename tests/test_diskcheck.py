"""The low-disk check must be seen going RED, not just green.

`deploy/diskcheck.sh` exists because / on the deployment box — the disk prod
serves from — hit 100% twice, and on both nights the backup silently did not
run and nothing said so (de-yef, de-o4e). A check that has only ever been
observed passing is not known to work, so most of what is below drives it into
each condition it claims to catch and asserts on the exit status, the message,
and whether a push actually left the script.

`df` and `curl` are the only external calls, so both are stubbed with PATH
shims. That keeps the suite in the unit tier: no real filesystem is measured, no
credentials are read, and no test can push a notification anywhere.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "deploy" / "diskcheck.sh"

PUSHOVER_URL = "https://pushover.example/messages.json"

# Answers df from a table keyed by path: source, target, avail (1K blocks),
# percent. Prints a header line first, exactly as df does, because the script
# reads every field with `tail -n1`.
DF_STUB = r"""#!/usr/bin/env bash
path="${@: -1}"
row="$(grep -m1 -P "^\Q${path}\E\t" "$DF_TABLE")" || {
    echo "df-stub: no table row for ${path}" >&2; exit 1; }
IFS=$'\t' read -r _ src tgt avail pcent <<< "$row"
for arg in "$@"; do
    case "$arg" in
        --output=avail)  echo "Avail";      echo "$avail";       exit 0 ;;
        --output=source) echo "Filesystem"; echo "$src";         exit 0 ;;
        --output=target) echo "Mounted on"; echo "$tgt";         exit 0 ;;
        --output=pcent)  echo "Use%";       echo "${pcent}%";    exit 0 ;;
    esac
done
# `df -h <path>`, used only to quote a human-readable line into the message.
echo "Filesystem Size Used Avail Use% Mounted on"
echo "$src - - - ${pcent}% $tgt"
"""

# A df that cannot answer at all. "We could not measure anything" must not be
# reported the same way as "everything is fine".
DF_BROKEN = """#!/usr/bin/env bash
exit 1
"""

CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$CURL_CALL_LOG"
exit 0
"""

GB = 1024 * 1024  # 1K blocks in a gigabyte


class Rig:
    """A throwaway box: a df table, a config dir, and a recorded curl."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("df", DF_STUB), ("curl", CURL_STUB)):
            stub = self.bin / name
            stub.write_text(body)
            stub.chmod(0o755)

        self.table = tmp_path / "df.tsv"
        self.rows = []
        self.conf = tmp_path / "config"
        self.conf.mkdir()
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.curl_log = tmp_path / "curl.log"
        self.alerts = {
            "PUSHOVER_TOKEN": "tok",
            "PUSHOVER_USER": "usr",
            "PUSHOVER_API_URL": PUSHOVER_URL,
        }

    def disk(self, path, *, source, target, free_gb, pcent):
        avail = int(free_gb * GB)
        self.rows.append(f"{path}\t{source}\t{target}\t{avail}\t{pcent}")
        return self

    def store_env(self, root):
        (self.conf / "store.env").write_text(f"MTGC_STORE_ROOT={root}\n")
        return self

    def run(self, *args, env=None):
        self.table.write_text("\n".join(self.rows) + "\n")
        (self.conf / "alerts.env").write_text(
            "".join(f"{k}={v}\n" for k, v in self.alerts.items())
        )
        full = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "MTGC_CONFIG_DIR": str(self.conf),
            "DF_TABLE": str(self.table),
            "CURL_CALL_LOG": str(self.curl_log),
        }
        full.update(env or {})
        return subprocess.run(
            ["bash", str(CHECK), *args],
            capture_output=True,
            text=True,
            env=full,
        )

    @property
    def pushes(self):
        if not self.curl_log.exists():
            return []
        return [ln for ln in self.curl_log.read_text().splitlines() if ln.strip()]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def home_disk(rig, *, free_gb=50, pcent=50):
    return rig.disk(
        str(rig.home), source="/dev/prod", target="/", free_gb=free_gb, pcent=pcent
    )


# --- Alert mode -------------------------------------------------------------


def test_healthy_disk_alerts_nobody(rig):
    home_disk(rig, pcent=55)
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert "at 55%" in r.stdout
    assert rig.pushes == []


def test_full_disk_pushes_an_alert_naming_the_mount(rig):
    home_disk(rig, pcent=98, free_gb=2)
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert len(rig.pushes) == 1
    push = rig.pushes[0]
    assert PUSHOVER_URL in push
    assert "MTGC LOW DISK / (98%)" in push


def test_threshold_is_inclusive(rig):
    """At exactly the threshold the disk is already too full to be quiet about."""
    home_disk(rig, pcent=90)
    assert rig.run().returncode == 0
    assert len(rig.pushes) == 1


def test_threshold_is_configurable(rig):
    home_disk(rig, pcent=80)
    rig.alerts["MTGC_DISK_THRESHOLD"] = "75"
    rig.run()
    assert len(rig.pushes) == 1


def test_the_environment_beats_the_config_file(rig):
    """`MTGC_DISK_THRESHOLD=0 bash diskcheck.sh` is the prove-it-goes-red recipe.

    Sourcing a dotenv always overwrites, so on a box that has configured a
    threshold the recipe would silently do nothing without this precedence —
    which is the exact class of defect this check exists to remove.
    """
    home_disk(rig, pcent=55)
    rig.alerts["MTGC_DISK_THRESHOLD"] = "90"
    r = rig.run(env={"MTGC_DISK_THRESHOLD": "0"})
    assert "threshold 0%" in r.stdout
    assert len(rig.pushes) == 1


def test_the_environment_beats_the_config_file_for_the_floor_too(rig):
    home_disk(rig, free_gb=42)
    rig.alerts["MTGC_DISK_FLOOR_GB"] = "10"
    assert rig.run("--floor", env={"MTGC_DISK_FLOOR_GB": "100"}).returncode != 0


def test_unable_to_alert_is_a_failure_not_a_no_op(rig):
    """A full disk that reached nobody must fail the unit, which is how it gets seen."""
    home_disk(rig, pcent=99)
    rig.alerts = {}
    r = rig.run()
    assert r.returncode != 0
    assert "reached nobody" in r.stderr
    assert rig.pushes == []


def test_measuring_nothing_is_a_failure_not_a_quiet_pass(rig):
    """A df that cannot answer must not exit 0 having checked no disk."""
    home_disk(rig, pcent=99)
    (rig.bin / "df").write_text(DF_BROKEN)
    r = rig.run()
    assert r.returncode != 0
    assert "measured no filesystem at all" in r.stderr
    assert rig.pushes == []


def test_the_gate_also_refuses_to_pass_when_it_cannot_measure(rig):
    home_disk(rig, free_gb=1)
    (rig.bin / "df").write_text(DF_BROKEN)
    r = rig.run("--floor")
    assert r.returncode != 0
    assert "measured no filesystem at all" in r.stderr


# --- Which filesystems are watched ------------------------------------------


def test_store_root_on_another_device_is_watched_too(rig):
    """The non-prod store is a second disk, and it is the one rigs fill."""
    home_disk(rig, pcent=50)
    store = rig.tmp / "store"
    store.mkdir()
    rig.disk(str(store), source="/dev/big", target="/workspaces", free_gb=700, pcent=95)
    rig.store_env(store)

    r = rig.run()
    assert "/ at 50%" in r.stdout
    assert "/workspaces at 95%" in r.stdout
    assert len(rig.pushes) == 1
    assert "MTGC LOW DISK /workspaces (95%)" in rig.pushes[0]


def test_no_store_configured_watches_exactly_one_filesystem(rig):
    home_disk(rig, pcent=99)
    r = rig.run()
    assert r.stdout.count("diskcheck:") == 1
    assert len(rig.pushes) == 1


def test_store_on_the_same_device_is_reported_once(rig):
    """Two paths on one disk are one check, not one alarm per alias."""
    home_disk(rig, pcent=99)
    store = rig.tmp / "same"
    store.mkdir()
    rig.disk(str(store), source="/dev/prod", target="/", free_gb=2, pcent=99)
    rig.store_env(store)

    r = rig.run()
    assert r.stdout.count("diskcheck:") == 1
    assert len(rig.pushes) == 1


def test_explicit_empty_store_root_overrides_store_env(rig):
    """An explicit empty value is how a single run opts back out of the store."""
    home_disk(rig, pcent=50)
    store = rig.tmp / "store"
    store.mkdir()
    rig.disk(str(store), source="/dev/big", target="/workspaces", free_gb=700, pcent=95)
    rig.store_env(store)

    r = rig.run(env={"MTGC_STORE_ROOT": ""})
    assert r.stdout.count("diskcheck:") == 1
    assert "/workspaces" not in r.stdout
    assert rig.pushes == []


# --- Floor mode -------------------------------------------------------------


def test_floor_passes_with_room(rig):
    home_disk(rig, free_gb=42)
    r = rig.run("--floor")
    assert r.returncode == 0, r.stderr
    assert "has 42G free (floor 10G) — ok" in r.stdout


def test_floor_fails_without_room(rig):
    home_disk(rig, free_gb=3)
    r = rig.run("--floor")
    assert r.returncode != 0
    assert "only 3G free on / (floor 10G)" in r.stderr
    # The message has to explain that this will NOT look like a disk error later.
    assert "Bus error" in r.stderr


def test_floor_truncates_rather_than_rounding_up(rig):
    """`df -BG` reports 9.2G free as 10G, which would clear a 10G floor.

    The floor exists to be conservative, so the script reads 1K blocks and
    divides. 9.2G free must fail a 10G floor.
    """
    home_disk(rig, free_gb=9.2)
    r = rig.run("--floor")
    assert r.returncode != 0
    assert "only 9G free" in r.stderr


def test_floor_is_configurable(rig):
    home_disk(rig, free_gb=42)
    rig.alerts["MTGC_DISK_FLOOR_GB"] = "100"
    assert rig.run("--floor").returncode != 0


def test_floor_checks_an_explicitly_named_path(rig):
    home_disk(rig, free_gb=99)
    store = rig.tmp / "store"
    store.mkdir()
    rig.disk(str(store), source="/dev/big", target="/workspaces", free_gb=1, pcent=99)
    r = rig.run("--floor", str(store))
    assert r.returncode != 0
    assert "/workspaces" in r.stderr
    assert "/dev/prod" not in r.stderr


def test_floor_reports_one_device_once(rig):
    home_disk(rig, free_gb=1)
    alias = rig.tmp / "alias"
    alias.mkdir()
    rig.disk(str(alias), source="/dev/prod", target="/", free_gb=1, pcent=99)
    r = rig.run("--floor", str(rig.home), str(alias))
    assert r.returncode != 0
    assert r.stderr.count("only 1G free") == 1


def test_floor_measures_a_store_root_that_does_not_exist_yet(rig):
    """A store directory is created by the run being gated, not before it."""
    home_disk(rig, free_gb=1)
    missing = rig.home / "not" / "created" / "yet"
    r = rig.run("--floor", str(missing))
    assert r.returncode != 0
    assert "only 1G free on /" in r.stderr


def test_floor_reports_every_short_disk_not_just_the_first(rig):
    home_disk(rig, free_gb=1)
    store = rig.tmp / "store"
    store.mkdir()
    rig.disk(str(store), source="/dev/big", target="/workspaces", free_gb=2, pcent=99)
    r = rig.run("--floor", str(rig.home), str(store))
    assert r.returncode != 0
    assert "only 1G free on /" in r.stderr
    assert "only 2G free on /workspaces" in r.stderr


def test_floor_never_pushes(rig):
    """The gate reports to its caller. Alerting is the timer's job."""
    home_disk(rig, free_gb=1)
    rig.run("--floor")
    assert rig.pushes == []


# --- Deployment wiring ------------------------------------------------------


def test_the_timer_unit_is_installed_and_torn_down():
    setup = (REPO_ROOT / "deploy" / "setup.sh").read_text()
    teardown = (REPO_ROOT / "deploy" / "teardown.sh").read_text()
    assert "mtgc-diskcheck" in setup
    assert "mtgc-diskcheck" in teardown


def test_the_unit_alerts_on_failure_and_writes_nothing():
    unit = (REPO_ROOT / "deploy" / "mtgc-diskcheck.service").read_text()
    # Alert mode reports a full disk through alert.sh, and reports its own
    # inability to do so by failing -- so the alert has to be wired to the unit
    # too, or that second case is a red unit nobody hears about.
    assert "OnFailure=mtgc-alert-{{INSTANCE}}@%n.service" in unit
    exec_line = unit.split("ExecStart=")[1].splitlines()[0]
    assert exec_line.endswith("deploy/diskcheck.sh'")
    # A checker that could free space on its own is a liability: what to delete
    # is a judgement a timer cannot make. It runs df and nothing else.
    assert "--floor" not in exec_line
    for writer in ("rm ", "prune", "podman"):
        assert writer not in exec_line


def test_the_installed_unit_is_the_default_alert_mode_not_the_gate():
    """A timer that exits non-zero on a merely-lowish disk would cry wolf.

    Alert mode's non-zero exit means the push failed, which is worth a page.
    Gate mode's means "not enough room for the work you were about to start",
    which is a caller's answer, not a nightly one.
    """
    unit = (REPO_ROOT / "deploy" / "mtgc-diskcheck.service").read_text()
    assert "diskcheck.sh --floor" not in unit


def test_setup_gates_on_room_before_it_builds():
    setup = (REPO_ROOT / "deploy" / "setup.sh").read_text()
    gate = setup.index("diskcheck.sh")
    build = setup.index("podman build")
    assert gate < build, "the floor check must run before the image build"
    line = setup[:gate].rsplit("\n", 1)[-1] + setup[gate:].splitlines()[0]
    assert "--floor" in line
    # Gated against the store this run resolved, not a hardcoded default --
    # otherwise a non-prod bring-up measures prod's disk and vice versa.
    assert '"${MTGC_STORE_ROOT:-$HOME}"' in line


def test_deploy_gates_on_room_before_it_rebuilds():
    """deploy.sh is prod's redeploy path — a build that runs out mid-way leaves
    a partial image and then restarts the live service against it."""
    deploy = (REPO_ROOT / "deploy" / "deploy.sh").read_text()
    gate = deploy.index("diskcheck.sh")
    assert gate < deploy.index("podman build")
    # After the store is adopted from the instance's own unit, so it measures
    # the disk this instance actually builds into.
    assert deploy.index("mtgc_store_adopt_instance") < gate


def test_ci_gates_on_room_before_it_builds():
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    gate = ci.index("diskcheck.sh --floor")
    # The store has to be selected first, or the gate measures the wrong disk.
    assert ci.index("Select container store") < gate
    assert gate < ci.index("store-isolation-gate.sh")
