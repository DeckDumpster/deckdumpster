"""The scheduled catalogue refresh must be one step, and must fail out loud.

`mtg data refresh-catalog` exists because the two halves of a catalogue refresh
-- `mtg cache all` for Scryfall's sets and printings, `mtg data fetch` for
MTGJSON -- were both by hand, and the catalogue sat two months behind upstream
(newest set 2026-06-26 against The Hobbit's 2026-08-14) while every timer on the
box was green (de-b5q filed the alarm, de-wdq this fix).

Two things make the scheduled unit worth having, and each is pinned below:

* it runs **both** halves, in one process, so there is no second command anyone
  has to remember and no half-refresh that reads as a success;
* its exit status is the truth. The MTGJSON import used to run inside a
  `try/except` that printed a warning, so a download whose import blew up left a
  current file on disk, a stale database, and a return code of 0 -- exactly the
  shape of failure that stayed invisible for two months.

No network: both halves are stubbed, because what is under test is the wiring
between them and not what either one downloads.
"""

import argparse
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from mtg_collector.cli import data_cmd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy"


# --- The command --------------------------------------------------------------


@contextmanager
def _stubbed_refresh(calls, *, cache_all=None):
    """Every side effect of build_catalog, recorded instead of performed."""
    from mtg_collector.landing import Replay, use_replay

    class _R(Replay):
        def __init__(self):
            self.run_id = "R"

    use_replay(_R())
    cache = cache_all or (lambda **kw: calls.append(("cache_all", kw)))
    try:
        with patch("mtg_collector.cli.cache_cmd.cache_all", side_effect=cache), \
             patch.object(data_cmd, "fetch_allprintings", side_effect=lambda **kw: calls.append(("fetch", kw))), \
             patch("mtg_collector.db.connection.get_connection", side_effect=lambda p: ("conn", p)), \
             patch("mtg_collector.db.schema.rebuild_collection_card_names",
                   side_effect=lambda conn: calls.append(("resync", {"db_path": conn[1]})) or 0):
            yield
    finally:
        from mtg_collector.landing import reset_run
        reset_run()


def test_it_runs_every_half_in_one_call():
    """Scryfall cache, MTGJSON, then the collection's copy of the card name.

    One invocation for all of it. That is the whole point.
    """
    calls = []
    with _stubbed_refresh(calls):
        data_cmd.build_catalog("/tmp/whatever.sqlite")

    # Scryfall first: `sets` is what check-catalog measures, so on a run that
    # only half-lands, the half that landed is the half the alarm can see. The
    # resync last: it copies from printings.card_name, which `cache all` is what
    # repairs.
    assert [name for name, _ in calls] == ["cache_all", "fetch", "resync"]
    # Every half writes the database it was pointed at, not the default one --
    # including the resync, whose target is the *instance* DB even under
    # split-DB, where the other two write the shared catalogue.
    assert [kw["db_path"] for _, kw in calls] == ["/tmp/whatever.sqlite"] * 3


def test_the_mtgjson_half_re_downloads_unconditionally():
    """`fetch` skips a file that already exists unless forced, and a skip here is
    indistinguishable from a run with nothing to do. MTGJSON rebuilds daily."""
    calls = []
    with _stubbed_refresh(calls):
        data_cmd.build_catalog("/tmp/whatever.sqlite")

    fetch_kwargs = [kw for name, kw in calls if name == "fetch"]
    assert [kw["force"] for kw in fetch_kwargs] == [True]


def test_a_failing_scryfall_half_stops_the_run():
    """No swallowing: the MTGJSON half must not paper over a dead Scryfall half."""
    calls = []
    with _stubbed_refresh(calls, cache_all=_raise_scryfall), \
         patch.object(data_cmd, "fetch_allprintings") as fetch:
        with pytest.raises(RuntimeError):
            data_cmd.build_catalog("/tmp/whatever.sqlite")

    assert fetch.call_count == 0


def test_the_refresh_lands_then_derives_that_run():
    """refresh = land + derive of the run it landed; no build of its own."""
    calls = []
    with patch.object(data_cmd, "land_catalog", side_effect=lambda: calls.append("land") or "RUN1"), \
         patch.object(data_cmd, "derive_catalog",
                      side_effect=lambda db, **kw: calls.append(("derive", db, kw["run_id"]))), \
         patch.object(data_cmd, "build_catalog", side_effect=lambda db: calls.append("build")):
        data_cmd.refresh_catalog("/tmp/x.sqlite")
    assert calls == ["land", ("derive", "/tmp/x.sqlite", "RUN1")]


def test_a_refresh_whose_derive_fails_fails():
    with patch.object(data_cmd, "land_catalog", return_value="RUN1"), \
         patch.object(data_cmd, "derive_catalog", side_effect=RuntimeError("derive down")):
        with pytest.raises(RuntimeError):
            data_cmd.refresh_catalog("/tmp/x.sqlite")


def _raise_scryfall(**_kw):
    raise RuntimeError("scryfall down")


def test_a_failing_import_fails_the_command(tmp_path, monkeypatch):
    """The regression this bead is named after, at the smallest scale that shows it.

    A downloaded AllPrintings.json whose import raises used to print a warning and
    return normally -- so `podman exec ... mtg data fetch` exited 0, the timer went
    green, and the database stayed stale.
    """
    dest = tmp_path / "AllPrintings.json"
    monkeypatch.setattr(data_cmd, "get_allprintings_path", lambda: dest)
    monkeypatch.setattr(data_cmd, "_download", lambda url, path, **kw: path.write_bytes(_gzipped(b"{}")))
    monkeypatch.setattr(data_cmd, "import_mtgjson", _raise)

    with pytest.raises(RuntimeError):
        data_cmd.fetch_allprintings(force=True, db_path=str(tmp_path / "db.sqlite"))


def test_the_import_follows_the_db_path_it_was_given(tmp_path, monkeypatch):
    """It used to import into get_db_path() regardless of --db."""
    dest = tmp_path / "AllPrintings.json"
    monkeypatch.setattr(data_cmd, "get_allprintings_path", lambda: dest)
    monkeypatch.setattr(data_cmd, "_download", lambda url, path, **kw: path.write_bytes(_gzipped(b"{}")))
    monkeypatch.setattr(data_cmd, "_fetch_mtgjson_version", lambda: None)
    seen = []
    monkeypatch.setattr(data_cmd, "import_mtgjson", seen.append)

    target = str(tmp_path / "explicit.sqlite")
    data_cmd.fetch_allprintings(force=True, db_path=target)
    assert seen == [target]


def test_the_subcommand_is_registered():
    """It has to be reachable as `mtg data refresh-catalog`, which is what the unit runs."""
    parser = argparse.ArgumentParser()
    data_cmd.register(parser.add_subparsers(dest="command"))
    parsed = parser.parse_args(["data", "refresh-catalog"])
    assert parsed.data_command == "refresh-catalog"


def test_the_freshness_check_points_at_it():
    """A red alarm should name the one command that clears it, not the two that
    have to be remembered in order."""
    source = (REPO_ROOT / "mtg_collector" / "cli" / "data_cmd.py").read_text()
    fix = [ln for ln in source.splitlines() if 'print("Fix:' in ln]
    assert len(fix) == 1
    assert "refresh-catalog" in fix[0]


# --- Deployment wiring --------------------------------------------------------


def test_the_old_refresh_timer_is_retired():
    """The 01:00 refresh is the chain's land and derive links now (lakehouse 14);
    a surviving template would install a second writer of the catalogue."""
    assert not (DEPLOY / "mtgc-catalog-refresh.timer").exists()
    assert not (DEPLOY / "mtgc-catalog-refresh.service").exists()


def test_the_freshness_check_runs_after_the_chain_that_it_grades():
    check = (DEPLOY / "mtgc-catalog-check.timer").read_text()
    assert "OnCalendar=*-*-* 09:00:00" in check
    land = (DEPLOY / "mtgc-land.timer").read_text()
    assert "OnCalendar=*-*-* 08:00:00 UTC" in land


# --- Helpers ------------------------------------------------------------------


def _gzipped(payload: bytes) -> bytes:
    import gzip
    import io

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(payload)
    return buf.getvalue()


def _raise(*args, **kwargs):
    raise RuntimeError("import blew up")
