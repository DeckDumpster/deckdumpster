"""The disk floor gate must be seen refusing, and be seen wired in (de-3ww).

`deploy/diskcheck.sh` exists because a build that runs out of room does not fail
as a disk error — the deployment box's `/` has hit 100% twice, once producing
`ld terminated with signal 7 [Bus error]` from a link step, which reads as a
broken toolchain and cost real diagnosis time. A gate whose refusal has never
been observed is not known to refuse, so most of what is below drives the
shipped script under its floor and asserts on the exit status and the message.

`df` is the script's only external call, so it is stubbed with a PATH shim that
replays a canned table. That keeps this in the unit tier and — more usefully —
lets a test say "this filesystem has 3G free" without needing a filesystem that
does.

The last section asserts something the script cannot assert about itself: that
the paths which build images actually call it, and call it *before* the build.
A gate nobody invokes is the same as no gate, and that is a one-line regression.
"""

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "deploy" / "diskcheck.sh"

GB = 1024 * 1024  # KiB in a GiB, which is the unit `df -Pk` reports.

# Replays DF_TABLE for whatever path it is handed: one row per line, as
#   <path> <source> <avail_kb> <mount>
# and emits it in the POSIX `df -P` shape the script parses. `df -h` (the
# diagnostic line on failure) gets the same row rendered loosely — the script
# only echoes it.
DF_STUB = r"""#!/usr/bin/env bash
argv="$*"
target="${!#}"
row="$(grep -E "^${target}[[:space:]]" "$DF_TABLE" | head -n1)"
if [ -z "$row" ]; then
    echo "df: ${target}: No such file or directory" >&2
    exit 1
fi
set -- $row
src="$2"; avail="$3"; mount="$4"
case "$argv" in
    *-h*) echo "Filesystem Size Used Avail Use% Mounted on"
          echo "$src 100G 90G $((avail / 1024 / 1024))G 90% $mount" ;;
    *)    echo "Filesystem 1024-blocks Used Available Capacity Mounted on"
          echo "$src 104857600 0 $avail 50% $mount" ;;
esac
"""


def _run(tmp_path, table, *, paths=("home",), env=None, bare=False):
    """Run the shipped script against a canned set of filesystems.

    `table` rows are (name, source, avail_kb, mount). Each name becomes a real
    directory under tmp_path, because the script walks up from a path that does
    not exist yet — behaviour of its own, exercised separately below rather
    than accidentally in every case.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "df"
    stub.write_text(DF_STUB)
    stub.chmod(0o755)

    rows = []
    for name, source, avail, mount in table:
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        rows.append(f"{d} {source} {avail} {mount}\n")
    (tmp_path / "df-table").write_text("".join(rows))

    conf = tmp_path / "conf"
    conf.mkdir(exist_ok=True)

    child = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DF_TABLE": str(tmp_path / "df-table"),
        # Never read the operator's real ~/.config/mtgc/alerts.env.
        "MTGC_CONFIG_DIR": str(conf),
    }
    child.pop("MTGC_DISK_FLOOR_GB", None)
    child.update(env or {})

    args = [] if bare else ["--floor", *(str(tmp_path / p) for p in paths)]
    return subprocess.run(
        ["bash", str(CHECK), *args],
        capture_output=True, text=True, env=child, cwd=tmp_path,
    )


ROOMY = [("home", "/dev/sda1", 40 * GB, "/")]
CRAMPED = [("home", "/dev/sda1", 3 * GB, "/")]


# ── Green, and what green means ─────────────────────────────────────────────


def test_a_roomy_disk_passes(tmp_path):
    proc = _run(tmp_path, ROOMY, paths=("home",))
    assert proc.returncode == 0, proc.stderr
    assert "40G free" in proc.stdout
    assert "ok" in proc.stdout


def test_the_default_floor_is_ten_gigabytes(tmp_path):
    """Documented in the header and in deploy/README.md; pin it here too."""
    proc = _run(tmp_path, ROOMY, paths=("home",))
    assert "floor 10G" in proc.stdout


# ── Every refusal it exists to make ─────────────────────────────────────────


def test_a_cramped_disk_refuses(tmp_path):
    proc = _run(tmp_path, CRAMPED, paths=("home",))
    assert proc.returncode == 1, proc.stdout
    assert "only 3G free on /" in proc.stderr


def test_the_refusal_says_why_the_build_would_not_have_looked_like_disk(tmp_path):
    """The whole point: the message has to pre-empt the misdiagnosis."""
    proc = _run(tmp_path, CRAMPED, paths=("home",))
    assert "Bus error" in proc.stderr
    assert "Free space before re-running" in proc.stderr


def test_a_path_it_cannot_measure_is_a_refusal_not_a_pass(tmp_path):
    """A gate that does not know the free space must not be the thing that
    says there is enough."""
    proc = _run(tmp_path, ROOMY, paths=("unmeasured",))
    assert proc.returncode == 1, proc.stdout
    assert "could not measure" in proc.stderr


def test_a_store_root_that_does_not_exist_yet_is_measured_on_its_parent(tmp_path):
    """MTGC_STORE_ROOT names a directory the first run has yet to create. It
    still sits on some mounted filesystem, and that is the one to ask."""
    proc = _run(tmp_path, CRAMPED, paths=("home/not-created-yet",))
    assert proc.returncode == 1, proc.stdout
    assert "only 3G free on /" in proc.stderr


def test_bare_invocation_is_a_usage_error_not_a_silent_pass(tmp_path):
    proc = _run(tmp_path, ROOMY, bare=True)
    assert proc.returncode == 2
    assert "Usage:" in proc.stderr


def test_an_unusable_floor_is_a_refusal_not_a_pass(tmp_path):
    """`MTGC_DISK_FLOOR_GB=lots` must not silently compare as zero."""
    proc = _run(tmp_path, CRAMPED, paths=("home",),
                env={"MTGC_DISK_FLOOR_GB": "lots"})
    assert proc.returncode == 2
    assert "not a whole number" in proc.stderr


# ── Both disks, counted once each ───────────────────────────────────────────


def test_the_store_disk_is_checked_even_when_home_is_roomy(tmp_path):
    """MTGC_STORE_ROOT moves the container store; it does not move $HOME. A
    build can still die on either, so a pass on one is not a pass."""
    table = [("home", "/dev/sda1", 40 * GB, "/"),
             ("big/store", "/dev/sdb1", 2 * GB, "/big")]
    proc = _run(tmp_path, table, paths=("home", "big/store"))
    assert proc.returncode == 1, proc.stdout
    assert "40G free" in proc.stdout        # the roomy one still reported...
    assert "only 2G free on /big" in proc.stderr   # ...and the cramped one named


def test_one_filesystem_under_two_names_is_reported_once(tmp_path):
    """With MTGC_STORE_ROOT unset every caller passes $HOME twice."""
    table = [("home", "/dev/sda1", 40 * GB, "/")]
    proc = _run(tmp_path, table, paths=("home", "home"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("40G free") == 1


def test_a_failure_on_the_first_disk_does_not_hide_the_second(tmp_path):
    """One red run should name every disk that is short, not just the first."""
    table = [("home", "/dev/sda1", 1 * GB, "/"),
             ("big/store", "/dev/sdb1", 2 * GB, "/big")]
    proc = _run(tmp_path, table, paths=("home", "big/store"))
    assert proc.returncode == 1
    assert "only 1G free on /" in proc.stderr
    assert "only 2G free on /big" in proc.stderr


# ── Host config ─────────────────────────────────────────────────────────────


def test_the_floor_can_be_raised_host_wide(tmp_path):
    """How much room this box must keep free is a fact about the box."""
    conf = tmp_path / "conf"
    conf.mkdir(exist_ok=True)
    (conf / "alerts.env").write_text("MTGC_DISK_FLOOR_GB=50\n")
    proc = _run(tmp_path, ROOMY, paths=("home",))
    assert proc.returncode == 1, proc.stdout
    assert "only 40G free on / (floor 50G)" in proc.stderr


def test_the_environment_outranks_the_host_file(tmp_path):
    conf = tmp_path / "conf"
    conf.mkdir(exist_ok=True)
    (conf / "alerts.env").write_text("MTGC_DISK_FLOOR_GB=50\n")
    proc = _run(tmp_path, ROOMY, paths=("home",),
                env={"MTGC_DISK_FLOOR_GB": "5"})
    assert proc.returncode == 0, proc.stderr
    assert "floor 5G" in proc.stdout


# ── It is actually wired in ─────────────────────────────────────────────────
#
# The gate's own tests cannot see this, and it is the failure that costs the
# whole feature: a script nobody calls is indistinguishable from no script.

BUILDERS = {
    "deploy/setup.sh": "podman build",
    "deploy/deploy.sh": "podman build",
    "deploy/seed.sh": "podman build",
}


def test_every_linux_build_path_calls_the_gate():
    for rel in BUILDERS:
        text = (REPO_ROOT / rel).read_text()
        assert "diskcheck.sh" in text, f"{rel} builds an image without the disk gate"


def test_the_gate_runs_before_the_build_not_after():
    """After the build it is a post-mortem, which is what we already had."""
    for rel, build in BUILDERS.items():
        lines = (REPO_ROOT / rel).read_text().splitlines()
        gate = next(i for i, ln in enumerate(lines) if "diskcheck.sh" in ln)
        first_build = next(i for i, ln in enumerate(lines)
                           if build in ln and not ln.lstrip().startswith("#"))
        assert gate < first_build, f"{rel} builds before it checks the disk"


def test_every_caller_checks_both_disks():
    """MTGC_STORE_ROOT moves the store, not $HOME. Checking only one leaves
    the build able to die on the other."""
    callers = list(BUILDERS) + [".github/workflows/ci.yml"]
    for rel in callers:
        text = (REPO_ROOT / rel).read_text()
        call = next(ln for ln in text.splitlines() if "diskcheck.sh" in ln)
        assert "--floor" in call, rel
        assert "$HOME" in call, rel
        assert "MTGC_STORE_ROOT" in call, rel


def test_ci_checks_the_disk_before_anything_builds():
    """The isolation gate builds an image too, so the check has to precede it
    rather than sit before the later `setup.sh` step."""
    lines = (REPO_ROOT / ".github/workflows/ci.yml").read_text().splitlines()
    gate = next(i for i, ln in enumerate(lines) if "diskcheck.sh" in ln)
    builds = [i for i, ln in enumerate(lines)
              if re.search(r"store-isolation-gate\.sh|setup\.sh \$INSTANCE", ln)]
    assert builds, "CI no longer builds anything — this test needs rewriting"
    assert gate < min(builds), "CI builds an image before checking the disk"
