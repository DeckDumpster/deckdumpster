"""Test-container discovery finds the container wherever its store is (de-1zq).

`MTGC_STORE_ROOT` (de-3mo) puts every non-prod instance in an alternate Podman
store, and a bare `podman` only ever sees the default one. The integration and
UI conftests used a bare `podman container exists`, so on an opted-in box the
documented local workflow

    bash deploy/setup.sh <inst> --test
    uv run pytest tests/integration/ --instance <inst>

found nothing and skipped — `124 skipped … exit 0`, which reads as a pass.

Two claims are tested here, and they are what the fix rests on:

* **The unit is the record.** Where a container *is* comes from the Quadlet
  systemd started it with, not from a variable saying where containers *should*
  go. That is what makes `--instance prod` resolve to the default store on a box
  whose `store.env` opts everything else in.
* **The masking is gone.** A named instance with no container is an error. A
  skip that exits 0 is exactly what this bead was filed about.

The store flags are asserted by driving the real `deploy/setup.sh` with podman
stubbed (as tests/test_deploy_store.py does), so the unit under test is a unit
the deploy path actually produces rather than one written by hand here.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.container_store import _env_global_args, discover_container, podman_argv

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP = REPO_ROOT / "deploy" / "setup.sh"

# Logs its argv, then answers `container exists` for one name only — which is
# how "was the lookup scoped to the right store" becomes observable: the stub
# is told which flags the container it knows about lives behind.
PODMAN_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PODMAN_LOG"
flags=""
while [ $# -gt 0 ]; do
    case "$1" in
        --root=*|--runroot=*) flags="$flags $1"; shift ;;
        *) break ;;
    esac
done
case "${1:-}" in
    container)
        [ "${2:-}" = "exists" ] || exit 0
        [ "${3:-}" = "${STUB_CONTAINER:-}" ] || exit 1
        [ "${flags# }" = "${STUB_FLAGS:-}" ] || exit 1
        exit 0
        ;;
    volume) exit 1 ;;
    --version) echo "podman version 0.0.0-stub" ;;
esac
exit 0
"""


class Box:
    """A fake host: an empty $HOME and a podman that only exists in one store."""

    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        stub = self.bin / "podman"
        stub.write_text(PODMAN_STUB)
        stub.chmod(0o755)
        for name in ("systemctl", "loginctl"):
            noop = self.bin / name
            noop.write_text("#!/usr/bin/env bash\nexit 0\n")
            noop.chmod(0o755)
        self.log = tmp_path / "podman.log"
        self.log.write_text("")
        self.store = tmp_path / "store"

    def env(self, **overrides):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["XDG_RUNTIME_DIR"] = str(self.tmp_path / "run")
        env["PODMAN_LOG"] = str(self.log)
        env.pop("MTGC_STORE_ROOT", None)
        env.pop("MTGC_STORE_GLOBAL_ARGS", None)
        # The stub answers `container exists` for this name behind these flags
        # and nothing else, so "found" and "found in the right store" are the
        # same assertion. Empty matches no container.
        env["STUB_CONTAINER"] = ""
        env["STUB_FLAGS"] = ""
        env.update(overrides)
        return env

    def apply(self, monkeypatch, **overrides):
        """Put this box's $HOME, PATH and store choice in front of the resolver."""
        for key, value in self.env(**overrides).items():
            monkeypatch.setenv(key, value)
        for key in ("MTGC_STORE_ROOT", "MTGC_STORE_GLOBAL_ARGS"):
            if key not in overrides:
                monkeypatch.delenv(key, raising=False)
        _env_global_args.cache_clear()

    def setup(self, instance, *args, store=None):
        env = self.env()
        if store is not None:
            env["MTGC_STORE_ROOT"] = str(store)
        result = subprocess.run(
            ["bash", str(SETUP), instance, "8083", *args],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def unit_flags(self, instance):
        """The GlobalArgs setup.sh recorded, as the stub would see them."""
        unit = self.home / ".config/containers/systemd" / f"mtgc-{instance}.container"
        for line in unit.read_text().splitlines():
            if line.startswith("GlobalArgs="):
                return line.split("=", 1)[1]
        return ""


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# --- Where the container is --------------------------------------------------


def test_an_alternate_store_instance_is_found(box, monkeypatch):
    """The bug itself: with the container in an alternate store, a bare podman
    saw nothing and the suite skipped itself green."""
    box.setup("alt", store=box.store)
    box.apply(
        monkeypatch,
        STUB_CONTAINER="systemd-mtgc-alt",
        STUB_FLAGS=box.unit_flags("alt"),
    )
    assert discover_container("alt") == "systemd-mtgc-alt"


def test_the_flags_come_from_the_instances_own_unit(box, monkeypatch):
    """Not re-derived here: the runroot is a hash of the graph root, and a second
    copy of that derivation is how the two drift apart."""
    box.setup("alt", store=box.store)
    box.apply(monkeypatch)
    graph = box.store / "storage"
    argv = podman_argv("alt")
    assert argv[0] == "podman"
    assert f"--root={graph}" in argv
    assert any(a.startswith("--runroot=") for a in argv[1:])
    assert " ".join(argv[1:]) == box.unit_flags("alt")


def test_an_unstamped_unit_means_the_default_store(box, monkeypatch):
    """An instance installed without a store gets no flags — that is a decision
    recorded by the absence of GlobalArgs, not a gap to fill in from elsewhere."""
    box.setup("plain")
    box.apply(monkeypatch)
    assert podman_argv("plain") == ["podman"]


def test_the_unit_beats_an_opted_in_environment(box, monkeypatch):
    """`--instance prod` on a box whose store.env opts everything else in.
    setup.sh excludes prod by name, so prod's container is in the DEFAULT store
    and the variable must not send the lookup somewhere else."""
    box.setup("plain")
    box.apply(monkeypatch, MTGC_STORE_ROOT=str(box.store))
    assert podman_argv("plain") == ["podman"]


def test_an_instance_with_no_unit_falls_back_to_the_environment(box, monkeypatch):
    """No unit is no record — macOS, where mac-setup.sh runs `podman run` and
    knows nothing about stores, or a container started by hand."""
    box.apply(monkeypatch, MTGC_STORE_ROOT=str(box.store))
    argv = podman_argv("never-installed")
    assert f"--root={box.store / 'storage'}" in argv


def test_nothing_is_flagged_without_a_store(box, monkeypatch):
    """Unset is a strict no-op, as everywhere else in this mechanism."""
    box.apply(monkeypatch)
    assert podman_argv("never-installed") == ["podman"]


def test_an_active_shim_is_not_flagged_twice(box, monkeypatch):
    """CI activates the shim and exports it through GITHUB_PATH; the shim IS a
    podman that appends the flags, so adding them here would pass each twice."""
    box.setup("alt", store=box.store)
    shim = box.store / "bin"
    box.apply(monkeypatch, MTGC_STORE_ROOT=str(box.store))
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    assert shim.joinpath("podman").is_file(), "setup.sh should have written the shim"
    assert podman_argv("alt") == ["podman"]


def test_a_container_in_another_store_is_not_found(box, monkeypatch):
    """The stub answers only for its own flags: an unflagged lookup must not
    resolve a container that lives behind --root."""
    box.setup("alt", store=box.store)
    box.apply(
        monkeypatch,
        STUB_CONTAINER="systemd-mtgc-alt",
        STUB_FLAGS=box.unit_flags("alt"),
    )
    (box.home / ".config/containers/systemd/mtgc-alt.container").unlink()
    assert discover_container("alt") is None


# --- The masking ------------------------------------------------------------


def _run_pytest(box, *args):
    env = box.env()
    env["PYTEST_ADDOPTS"] = ""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration/test_search_alias.py",
         "-p", "no:cacheprovider", *args],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )


def test_a_named_instance_with_no_container_fails(box):
    """The whole point: an all-skipped run exits 0 and reads as a pass."""
    result = _run_pytest(box, "--instance", "nonexistent-instance")
    assert result.returncode != 0, result.stdout
    assert "No container found for instance 'nonexistent-instance'" in result.stdout


def test_an_unasked_for_default_instance_still_skips(box):
    """`pytest tests/` collects tests/integration and must stay a unit run."""
    result = _run_pytest(box)
    assert result.returncode == 0, result.stdout
    assert "skipped" in result.stdout


# --- The regression guard ---------------------------------------------------


def test_no_conftest_shells_out_to_bare_podman():
    """Discovery lives in tests/container_store.py so there is one place for it
    to be right. A bare `podman` in a conftest is the bug, and it reappears by
    being written afresh rather than by anyone editing this rule."""
    offenders = []
    for path in sorted((REPO_ROOT / "tests").rglob("conftest.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if '"podman"' in line and "podman_argv" not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")
    assert offenders == [], offenders
