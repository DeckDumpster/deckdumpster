"""Catalog staleness measured by outcome, not by component health (de-b5q).

The card catalogue went two months without a new set -- 2026-06-26 (Marvel
Super Heroes) was the newest set in the database while upstream had shipped The
Hobbit on 2026-08-14 -- and every timer on the box was green the entire time.
Nothing was broken in the sense any of them test for: the price fetch ran, the
sealed catalogue imported, the backup uploaded, AllPrintings.json on disk had a
current mtime.  Each one answers "did my download succeed", and each one
answered yes, correctly, every single day.

The question none of them asks is the only one a user would: **is the catalogue
actually current?**  That is what this module answers, and it answers it the way
the answer is checkable -- by comparing what we hold against what exists:

    lag = (newest set released upstream) - (newest set released in our `sets`)

`mtg cache all` step 1 upserts *every* Scryfall set unfiltered, so `sets` is a
mirror of Scryfall's `/sets` list as of the last run.  Both sides of the
subtraction are therefore drawn from the same list under the same rule, and a
current mirror scores exactly 0 -- not "small", 0.  There is no release-cadence
term to tune around: a quiet month moves both sides together and the lag stays
0.  The lag leaves 0 only when a set is out in the world and our copy of the
list predates it.

Two consequences of "the same rule on both sides" that are load-bearing:

  * **Nothing is filtered by set_type or `digital`.**  Counting expansions
    upstream but everything locally (or the reverse) manufactures a lag that no
    refresh can close.  Whatever `mtg cache all` would store is what both sides
    count, which is all of it.

  * **Both sides drop sets with `released_at` in the future.**  Scryfall lists
    sets weeks before release -- as of the 2026-08-25 capture in
    tests/fixtures/, Reality Fracture (2026-10-02) through The Zeta Set
    (2026-12-31) -- and `mtg cache all` stores them the moment they appear.  A
    raw MAX(released_at) would read 2026-12-31 on both sides and the alarm
    would be measuring nothing at all.

Several sets normally share a release date -- 2026-08-14 carries The Hobbit, its
token set and The Hobbit Eternal -- so "the newest set" is settled by set code
among equals.  That tiebreak is deterministic and otherwise arbitrary, because
the comparison is between two *dates*; which of the day's sets gets named in the
one-line summary carries no weight, and the sets that actually went missing are
listed in full underneath it.

That upstream sets arrive in our copy *before* they release is also why the
threshold does not need to be generous.  A catalogue refreshed at any point
during a set's preview season already holds the row, so it scores 0 on release
day; a nonzero lag means the mirror predates the set's very appearance on
Scryfall, typically weeks earlier still.

**What this deliberately does not check:** that the *cards* of the newest set
were cached, only that the set is in the list.  The tempting stronger rule --
require printings for the set to count -- is a false-positive generator here:
`mtg cache all` skips every card with no oracle_id ("tokens, etc."), so a
token-only or art-series release such as `tmsh` / `thob` stores zero printings
by design and would hold the alarm red forever with no action able to clear it.
An alarm that cannot be cleared is an alarm that gets ignored, which is the
failure this whole bead exists to remove.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

#: How far the catalogue may fall behind upstream before it is stale.  A week
#: is already lenient given the preview-season slack described above: the real
#: 2026 gap would have tripped this on 2026-07-03, six weeks before anyone
#: noticed it by hand.  Override per instance with MTGC_CATALOG_MAX_LAG_DAYS.
DEFAULT_MAX_LAG_DAYS = 7

#: Cap on how many missing sets the verdict names.  The message is destined for
#: a Pushover push, which truncates at 1024 characters.
_MISSING_SHOWN = 8


@dataclass(frozen=True)
class SetStamp:
    """A set reduced to the three fields the comparison needs."""

    set_code: str
    set_name: str
    released_at: str

    def __str__(self) -> str:
        return f"{self.set_code} — {self.set_name} ({self.released_at})"


@dataclass(frozen=True)
class CatalogFreshness:
    """The verdict.  `stale` is derived, never passed in."""

    local: Optional[SetStamp]
    upstream: SetStamp
    #: Whole days between the two release dates, or None when the local
    #: catalogue holds no released set at all -- a distinct state, not a lag of
    #: some large number.
    lag_days: Optional[int]
    max_lag_days: int
    #: Released upstream sets with no row locally, oldest first.
    missing: Tuple[SetStamp, ...]

    @property
    def stale(self) -> bool:
        return self.lag_days is None or self.lag_days > self.max_lag_days

    def summary(self) -> str:
        """One line: both sides of the comparison, the lag, and the verdict.

        Dates, not set names.  Several sets share a release date and which one
        the tiebreak lands on says nothing -- the date is the measured quantity,
        and the sets that actually went missing are named by detail().
        """
        if self.local is None:
            return (
                "STALE — the local catalogue holds no released set at all; "
                f"upstream is at {self.upstream.released_at} "
                f"(threshold {self.max_lag_days}d)"
            )
        verdict = "STALE" if self.stale else "OK"
        return (
            f"{verdict} — local catalogue is at {self.local.released_at}, "
            f"upstream at {self.upstream.released_at}: lag {self.lag_days}d "
            f"({'>' if self.stale else '<='} {self.max_lag_days}d threshold)"
        )

    def detail(self) -> str:
        """The missing sets, for the alarm body.  Empty when none are."""
        if not self.missing:
            return ""
        shown = self.missing[:_MISSING_SHOWN]
        lines = [f"  {s}" for s in shown]
        if len(self.missing) > len(shown):
            lines.append(f"  ... and {len(self.missing) - len(shown)} more")
        return f"{len(self.missing)} released set(s) missing locally:\n" + "\n".join(lines)


def _released_stamps(rows: Iterable[Tuple[str, str, str]], today: date) -> List[SetStamp]:
    """Sets that have actually come out, oldest first.

    A row with no release date cannot be placed on the axis at all -- the
    ingest paths that create a set row from a collector number alone leave it
    NULL, and 174 of the 192 sets in tests/fixtures/test-data.sqlite are exactly
    that -- so it takes part in neither side of the comparison.
    """
    iso_today = today.isoformat()
    out = [
        SetStamp(code, name, released)
        for code, name, released in rows
        if released and released <= iso_today
    ]
    out.sort(key=lambda s: (s.released_at, s.set_code))
    return out


def local_released_sets(conn: sqlite3.Connection, today: date) -> List[SetStamp]:
    """Every released set the local catalogue holds, oldest first."""
    rows = conn.execute(
        "SELECT set_code, set_name, released_at FROM sets WHERE released_at IS NOT NULL"
    ).fetchall()
    return _released_stamps(((r[0], r[1], r[2]) for r in rows), today)


def upstream_released_sets(scryfall_sets: Sequence[Dict], today: date) -> List[SetStamp]:
    """Every released set Scryfall reports, oldest first.

    Takes the decoded `/sets` payload -- the same list `mtg cache all` upserts
    from -- so the check and the ingest cannot disagree about what a set is.
    """
    return _released_stamps(
        ((s["code"], s.get("name", s["code"]), s.get("released_at")) for s in scryfall_sets),
        today,
    )


def assess(
    conn: sqlite3.Connection,
    scryfall_sets: Sequence[Dict],
    today: date,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
) -> CatalogFreshness:
    """Compare the local set list against upstream's and return the verdict.

    Raises when upstream reports no released set at all.  That is not a fresh
    catalogue and it is not a stale one -- it means the question did not get
    asked, and "we could not ask" must never share an outcome with "the answer
    is fine".
    """
    upstream = upstream_released_sets(scryfall_sets, today)
    if not upstream:
        raise ValueError(
            "upstream reported no set released on or before "
            f"{today.isoformat()} — the catalogue could not be checked"
        )
    newest_upstream = upstream[-1]

    local = local_released_sets(conn, today)
    newest_local = local[-1] if local else None

    if newest_local is None:
        lag_days = None
        floor = ""
    else:
        lag_days = (
            date.fromisoformat(newest_upstream.released_at)
            - date.fromisoformat(newest_local.released_at)
        ).days
        floor = newest_local.released_at

    # What the lag is made of.  Everything released after the local high-water
    # mark that has no row here at all -- the "and here is what you are
    # missing" half of a message that would otherwise just be a number.
    # Codes are compared case-folded: Scryfall emits them lowercase and that is
    # what `mtg cache all` stores, but the by-hand ingest paths take a set code
    # from whatever the user typed, and a row that is present under `LCI` is
    # present.
    have = {code.lower() for (code,) in conn.execute("SELECT set_code FROM sets")}
    missing = tuple(
        s for s in upstream if s.released_at > floor and s.set_code.lower() not in have
    )

    return CatalogFreshness(
        local=newest_local,
        upstream=newest_upstream,
        lag_days=lag_days,
        max_lag_days=max_lag_days,
        missing=missing,
    )
