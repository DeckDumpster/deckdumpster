"""The catalog freshness alarm must be seen going RED on the gap it exists for.

`mtg data check-catalog` is the outcome check for the card catalogue (de-b5q).
Its whole reason to exist is that every component-health timer on the box stayed
green through a real two-month staleness gap, so an alarm demonstrated only in
the green is worth exactly as much as those were.

The centrepiece is therefore `test_the_real_2026_gap_fires`, which rebuilds the
catalogue as it actually stood -- newest set 2026-06-26, Marvel Super Heroes --
and compares it against the real Scryfall `/sets` payload captured on
2026-08-25 (tests/fixtures/scryfall-sets-2026-08-25.json), where the newest
released set is The Hobbit on 2026-08-14. Everything else here pins the
behaviours that keep that verdict trustworthy: no lag on a current mirror, no
phantom lag from unreleased sets, and a non-zero exit when upstream cannot be
asked at all.

No network: the upstream side is the captured fixture, and the CLI tests stub the
one call that would leave the process.
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from mtg_collector.db.catalog_freshness import (
    DEFAULT_MAX_LAG_DAYS,
    assess,
    local_released_sets,
    upstream_released_sets,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SETS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "scryfall-sets-2026-08-25.json"

# The real window from the bead. Both dates are facts about the fixture below,
# not chosen numbers -- see test_the_fixture_still_carries_the_real_window.
DB_NEWEST = date(2026, 6, 26)        # Marvel Super Heroes and its five siblings
UPSTREAM_NEWEST = date(2026, 8, 14)  # The Hobbit, its tokens, The Hobbit Eternal
REAL_LAG_DAYS = 49

# Six sets shipped on 2026-06-26 and three on 2026-08-14, so "the newest set" is
# settled by set code among equals. The comparison is between two dates; which of
# the day's sets gets named is deterministic and carries no weight, so the tests
# below assert the date as the fact and the code only as the tiebreak's output.
DB_NEWEST_CODE = "tmsh"
UPSTREAM_NEWEST_CODE = "thob"


@pytest.fixture(scope="module")
def upstream():
    """The real Scryfall /sets payload, as captured on 2026-08-25."""
    return json.loads(SETS_FIXTURE.read_text())["data"]


def make_db(sets):
    """An in-memory catalogue holding exactly these sets.

    Columns match `sets` in db/schema.py; only the three the check reads carry
    data, because those are the three `mtg cache all` step 1 writes for every
    Scryfall set before it touches a single card.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE sets (set_code TEXT PRIMARY KEY, set_name TEXT NOT NULL,"
        " set_type TEXT, released_at TEXT, digital INTEGER NOT NULL DEFAULT 0,"
        " cards_fetched_at TEXT, base_set_size INTEGER, total_set_size INTEGER)"
    )
    conn.executemany(
        "INSERT INTO sets (set_code, set_name, set_type, released_at, digital)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (s["code"], s["name"], s.get("set_type"), s.get("released_at"),
             1 if s.get("digital") else 0)
            for s in sets
        ],
    )
    return conn


def as_of(upstream, cutoff):
    """The upstream list as `mtg cache all` would have stored it on `cutoff`.

    Sets appear on Scryfall weeks before they release and the ingest stores them
    then, so a catalogue last refreshed on `cutoff` holds everything Scryfall
    listed by that date -- including future-dated ones. Trimming on
    `released_at` would model a mirror nobody has ever had.
    """
    iso = cutoff.isoformat()
    return [s for s in upstream if (s.get("released_at") or "") <= iso]


# --- The gap this alarm was built for ---------------------------------------


def test_the_fixture_still_carries_the_real_window(upstream):
    """The two dates in the bead are properties of the captured payload."""
    released = upstream_released_sets(upstream, date(2026, 8, 25))
    assert released[-1].released_at == UPSTREAM_NEWEST.isoformat()
    on_release_day = {s.set_code for s in released if s.released_at == UPSTREAM_NEWEST.isoformat()}
    assert on_release_day == {"hob", "thob", "hoc"}
    on_2026_06_26 = {s.set_code for s in released if s.released_at == DB_NEWEST.isoformat()}
    assert "msh" in on_2026_06_26
    # Nothing released between them, so the lag really is one clean gap.
    between = [
        s for s in released
        if DB_NEWEST.isoformat() < s.released_at < UPSTREAM_NEWEST.isoformat()
    ]
    assert between == []


def test_the_real_2026_gap_fires(upstream):
    """DB at 2026-06-26 vs upstream at 2026-08-14 must be STALE.

    This is the acceptance criterion, run against the real payload rather than a
    constructed one: a catalogue frozen the day Marvel Super Heroes shipped,
    checked on the day the bead was filed.
    """
    conn = make_db(as_of(upstream, DB_NEWEST))
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert verdict.stale
    assert verdict.lag_days == REAL_LAG_DAYS
    assert verdict.local.released_at == DB_NEWEST.isoformat()
    assert verdict.upstream.released_at == UPSTREAM_NEWEST.isoformat()
    assert verdict.local.set_code == DB_NEWEST_CODE
    assert verdict.upstream.set_code == UPSTREAM_NEWEST_CODE


def test_the_real_gap_names_the_sets_that_went_missing(upstream):
    """The alarm body says what is absent, not just how far behind we are."""
    conn = make_db(as_of(upstream, DB_NEWEST))
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert {s.set_code for s in verdict.missing} == {"hob", "thob", "hoc"}
    detail = verdict.detail()
    assert "The Hobbit" in detail
    assert "2026-08-14" in detail


def test_the_real_gap_would_have_fired_six_weeks_earlier(upstream):
    """The shipped threshold is not tuned to only just catch the known gap."""
    conn = make_db(as_of(upstream, DB_NEWEST))
    # 2026-08-14 + 7d, the first day the default threshold is exceeded.
    assert assess(conn, upstream, date(2026, 8, 21)).stale
    # And it stays red every day after, since nothing closes a lag but a refresh.
    assert assess(conn, upstream, date(2026, 8, 25)).stale


# --- The green cases that make the red ones mean something ------------------


def test_a_current_mirror_scores_exactly_zero(upstream):
    """Not "small". Zero -- both sides read the same set out of the same list."""
    conn = make_db(upstream)
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert verdict.lag_days == 0
    assert not verdict.stale
    assert verdict.missing == ()
    assert "OK" in verdict.summary()


def test_a_quiet_release_month_is_not_a_lag(upstream):
    """A gap between releases moves both sides together.

    Checked on 2026-08-13 — 48 days after the last release — a fully current
    catalogue is still current. An alarm keyed on "how old is our newest set"
    rather than "how far behind are we" would be red here, every time the
    calendar was quiet, and would be ignored by the time it mattered.
    """
    conn = make_db(upstream)
    verdict = assess(conn, upstream, date(2026, 8, 13))

    assert verdict.local.released_at == DB_NEWEST.isoformat()
    assert verdict.upstream.released_at == DB_NEWEST.isoformat()
    assert verdict.lag_days == 0
    assert not verdict.stale


def test_unreleased_sets_count_on_neither_side(upstream):
    """The fixture really does carry future sets, and they are excluded."""
    future = [s for s in upstream if (s.get("released_at") or "") > "2026-08-25"]
    assert {s["code"] for s in future} >= {"fra", "trk", "slz"}

    conn = make_db(upstream)
    verdict = assess(conn, upstream, date(2026, 8, 25))
    # A raw MAX(released_at) would read The Zeta Set (2026-12-31) on both sides.
    assert verdict.upstream.released_at == UPSTREAM_NEWEST.isoformat()
    assert verdict.local.released_at == UPSTREAM_NEWEST.isoformat()


def test_a_token_only_release_does_not_strand_the_alarm(upstream):
    """A set whose cards are never cached must still clear the alarm.

    `mtg cache all` skips every card with no oracle_id, so `thob` (The Hobbit
    Tokens) stores zero printings by design. Keying the local side on printings
    instead of on the set list would hold this red forever with nothing able to
    clear it.
    """
    conn = make_db(upstream)
    assert conn.execute(
        "SELECT COUNT(*) FROM sets WHERE set_code = 'thob'"
    ).fetchone()[0] == 1
    assert not assess(conn, upstream, date(2026, 8, 25)).stale


def test_digital_and_promo_sets_are_counted_the_same_on_both_sides(upstream):
    """Whatever the ingest stores, both sides count -- or the lag never closes."""
    conn = make_db(upstream)
    for kind in ("digital", "promo", "token", "memorabilia"):
        present = [
            s for s in upstream
            if (s.get("digital") if kind == "digital" else s.get("set_type") == kind)
        ]
        assert present, f"fixture carries no {kind} sets to check"
    assert assess(conn, upstream, date(2026, 8, 25)).lag_days == 0


# --- States that are not a lag ----------------------------------------------


def test_an_empty_catalogue_is_stale_but_is_not_a_number(upstream):
    conn = make_db([])
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert verdict.stale
    assert verdict.lag_days is None
    assert verdict.local is None
    assert "no released set in the local catalogue" in verdict.summary()


def test_sets_with_no_release_date_take_no_part(upstream):
    """174 of the 192 sets in the test fixture DB are exactly this shape."""
    conn = make_db(as_of(upstream, DB_NEWEST))
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at) VALUES ('zzz', 'Typed by hand', NULL)"
    )
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert verdict.local.released_at == DB_NEWEST.isoformat()
    assert verdict.lag_days == REAL_LAG_DAYS


def test_upstream_with_no_released_set_is_an_error_not_a_verdict(upstream):
    """"We could not ask" must not share an outcome with "the answer is fine"."""
    conn = make_db(upstream)
    with pytest.raises(ValueError, match="could not be checked"):
        assess(conn, [], date(2026, 8, 25))
    # Same for a payload that is all future sets: nothing to compare against.
    with pytest.raises(ValueError, match="could not be checked"):
        assess(conn, upstream, date(1990, 1, 1))


def test_a_set_code_stored_in_another_case_is_not_missing(upstream):
    """The by-hand ingest paths take the code the user typed."""
    conn = make_db(as_of(upstream, DB_NEWEST))
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at)"
        " VALUES ('HOB', 'The Hobbit', '2026-08-14')"
    )
    verdict = assess(conn, upstream, date(2026, 8, 25))

    assert not verdict.stale
    assert verdict.missing == ()


def test_local_released_sets_reads_the_real_test_fixture_db():
    """The shipped fixture DB is a real, trimmed catalogue -- run against it."""
    conn = sqlite3.connect(f"file:{REPO_ROOT / 'tests/fixtures/test-data.sqlite'}?mode=ro", uri=True)
    try:
        sets = local_released_sets(conn, date(2026, 8, 25))
    finally:
        conn.close()
    assert sets[-1].set_code == "ecl"
    assert sets[-1].released_at == "2026-01-23"


# --- Thresholds -------------------------------------------------------------


def test_the_threshold_is_a_strict_boundary(upstream):
    conn = make_db(as_of(upstream, DB_NEWEST))
    today = date(2026, 8, 25)
    assert not assess(conn, upstream, today, max_lag_days=REAL_LAG_DAYS).stale
    assert assess(conn, upstream, today, max_lag_days=REAL_LAG_DAYS - 1).stale


def test_the_shipped_default_is_a_week():
    assert DEFAULT_MAX_LAG_DAYS == 7


# --- The command itself -----------------------------------------------------
#
# `check_catalog` returns a process exit code and `mtg data check-catalog`
# sys.exit()s it, because the verdict travels on the unit's exit status and
# nothing else. Both halves are exercised: the code the function computes, and
# the fact that dispatch really turns it into the process's status.


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Drive the real command with the Scryfall call stubbed and today pinned."""
    from mtg_collector.cli import data_cmd

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 25)

    monkeypatch.setattr(data_cmd, "date", FrozenDate)

    def run(upstream_sets, db_sets, max_lag=None):
        db = tmp_path / "collection.sqlite"
        db.unlink(missing_ok=True)
        conn = make_db(db_sets)
        disk = sqlite3.connect(db)
        conn.backup(disk)
        disk.close()
        conn.close()

        class Stub:
            def get_all_sets(self):
                return list(upstream_sets)

        monkeypatch.setattr(
            "mtg_collector.services.scryfall.ScryfallAPI", Stub, raising=True
        )
        if max_lag is None:
            monkeypatch.delenv("MTGC_CATALOG_MAX_LAG_DAYS", raising=False)
        else:
            monkeypatch.setenv("MTGC_CATALOG_MAX_LAG_DAYS", max_lag)
        return data_cmd.check_catalog(str(db))

    return run


def test_cli_exits_1_on_the_real_gap(cli, upstream, capsys):
    rc = cli(upstream, as_of(upstream, DB_NEWEST))
    err = capsys.readouterr().err

    assert rc == 1
    assert "STALE" in err
    assert f"lag {REAL_LAG_DAYS}d" in err
    assert "The Hobbit" in err
    assert "mtg cache all" in err


def test_cli_exits_0_on_a_current_catalogue(cli, upstream, capsys):
    rc = cli(upstream, upstream)

    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_exits_1_when_upstream_cannot_be_asked(cli, upstream, capsys):
    """An empty Scryfall reply is a failed check, never a passing one.

    ScryfallAPI.get_all_sets() turns a request failure into an empty list, so
    this is the shape a network outage actually arrives in.
    """
    rc = cli([], upstream)

    assert rc == 1
    assert "Scryfall returned no sets" in capsys.readouterr().err


def test_cli_honours_the_threshold_override(cli, upstream):
    stale = as_of(upstream, DB_NEWEST)
    assert cli(upstream, stale, max_lag="60") == 0
    assert cli(upstream, stale, max_lag="7") == 1


def test_cli_rejects_a_threshold_that_is_not_a_number(cli, upstream, capsys):
    """A typo must not silently restore the shipped default."""
    rc = cli(upstream, upstream, max_lag="7 days")

    assert rc == 1
    assert "not an integer" in capsys.readouterr().err


def test_the_exit_code_reaches_the_process(monkeypatch, tmp_path, upstream):
    """`mtg data check-catalog` sys.exit()s the verdict.

    Without this the unit would succeed on a stale catalogue and OnFailure=
    would never fire -- a green timer over a red answer, which is the exact
    failure mode this check was built to end.
    """
    import argparse

    from mtg_collector.cli import data_cmd

    monkeypatch.setattr(data_cmd, "check_catalog", lambda db_path: 1)
    monkeypatch.setattr(
        "mtg_collector.db.connection.get_db_path", lambda p=None: str(tmp_path / "x.sqlite")
    )
    args = argparse.Namespace(data_command="check-catalog", db_path=None)
    with pytest.raises(SystemExit) as exit_info:
        data_cmd.run(args)
    assert exit_info.value.code == 1


def test_the_subcommand_is_registered():
    """It has to be reachable as `mtg data check-catalog`, which is what the unit runs."""
    import argparse

    from mtg_collector.cli import data_cmd

    parser = argparse.ArgumentParser()
    data_cmd.register(parser.add_subparsers(dest="command"))
    parsed = parser.parse_args(["data", "check-catalog"])
    assert parsed.data_command == "check-catalog"


# --- Deployment wiring ------------------------------------------------------


def test_the_timer_unit_is_installed_and_torn_down():
    setup = (REPO_ROOT / "deploy" / "setup.sh").read_text()
    teardown = (REPO_ROOT / "deploy" / "teardown.sh").read_text()
    assert "mtgc-catalog-check" in setup
    assert "mtgc-catalog-check" in teardown


def test_the_unit_alerts_on_failure_and_writes_nothing():
    unit = (REPO_ROOT / "deploy" / "mtgc-catalog-check.service").read_text()
    # The verdict travels on the unit's exit status, so the alert must be wired
    # to it -- otherwise a red check is a red unit nobody hears about.
    assert "OnFailure=mtgc-alert-{{INSTANCE}}@%n.service" in unit
    exec_line = unit.split("ExecStart=")[1].splitlines()[0]
    assert exec_line.endswith("mtg data check-catalog")
    # A checker that could damage what it watches is a liability.
    for writer in ("cache all", "data fetch", "data import", "rm "):
        assert writer not in exec_line
