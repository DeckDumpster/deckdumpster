"""`setup.sh --test` must build its fixture from an EMPTY temp volume (de-8eu).

The `--test` path populates `mtgc-<inst>-data-setup` with the fixture, runs
`mtg db split --shared-out ... --prune` against it, tars the result and removes
the volume. A run that dies anywhere between the create and that removal leaves
the volume behind with the split already applied — `collection.sqlite` pruned of
cards / printings / sets.

Reusing it is silent in both directions, which is why both are pinned here:

* `podman volume create` used to be `>/dev/null 2>&1 || true`, so an existing
  volume was adopted rather than reported.
* `db split` re-run against the pruned database copied zero rows into a fresh
  `shared.sqlite` and reported "Done!".

The instance that came out served 200s over a catalogue with no rows in it, and
that reads as a bug in whatever change was under test.
"""

import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mtg_collector.db.schema import init_db
from tests.test_deploy_store import REPO_ROOT, Host


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


# --- deploy/setup.sh -------------------------------------------------------


def test_the_fixture_volume_is_removed_before_it_is_created(host):
    """Start from nothing, so a killed earlier run cannot seed this one."""
    host.setup("inst", "8083", "--test", check=False)

    calls = host.calls()
    rm = next(i for i, c in enumerate(calls) if c == "volume rm -f mtgc-inst-data-setup")
    create = next(i for i, c in enumerate(calls) if c == "volume create mtgc-inst-data-setup")
    assert rm < create, calls


def test_a_fixture_volume_that_survives_the_removal_is_a_hard_error(host):
    """The removal is best-effort; `volume create` is the guarantee.

    The stub fails every `volume` call, which is the shape of a volume that is
    still there after the rm. Nothing may be populated on top of it — before
    de-8eu the `|| true` swallowed exactly this and the run carried on into
    `mtg setup --demo` against whatever the volume already held.
    """
    result = host.setup("inst", "8083", "--test", check=False)

    assert result.returncode != 0, result.stdout
    assert not [c for c in host.calls() if "setup --demo" in c], host.calls()


# --- mtg db split ----------------------------------------------------------


def _split(source, shared_out, prune=False):
    from mtg_collector.cli.db_cmd import run_split

    return run_split(
        SimpleNamespace(db_path=source, shared_out=shared_out, prune=prune)
    )


def _empty_db(path):
    conn = sqlite3.connect(str(path))
    init_db(conn)
    conn.commit()
    conn.close()


def test_splitting_an_already_pruned_source_fails(tmp_path):
    """0 rows in printings is never a split worth doing."""
    source = tmp_path / "collection.sqlite"
    _empty_db(source)

    with pytest.raises(SystemExit) as exc:
        _split(str(source), str(tmp_path / "shared.sqlite"), prune=True)

    assert "printings" in str(exc.value)


def test_a_refused_split_does_not_touch_the_shared_db(tmp_path):
    """It refuses BEFORE --shared-out is opened.

    Otherwise the refusal still costs the catalogue: the shared DB is created
    with the full schema and every shared table emptied on the way to copying
    nothing over it.
    """
    source = tmp_path / "collection.sqlite"
    _empty_db(source)
    shared = tmp_path / "shared.sqlite"
    shared.write_text("not a database, and still here afterwards")

    with pytest.raises(SystemExit):
        _split(str(source), str(shared), prune=True)

    assert shared.read_text() == "not a database, and still here afterwards"


def test_the_refusal_is_visible_from_the_command_line(tmp_path):
    """`mtg db split` exits non-zero and says why — a container build reads
    the exit code, not the stdout."""
    source = tmp_path / "collection.sqlite"
    _empty_db(source)

    result = subprocess.run(
        [sys.executable, "-c", "from mtg_collector.cli import main; main()",
         "--db", str(source),
         "db", "split", "--shared-out", str(tmp_path / "shared.sqlite"), "--prune"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )

    assert result.returncode != 0, result.stdout
    assert "nothing to split" in result.stderr
