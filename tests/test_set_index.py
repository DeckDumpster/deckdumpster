"""GET /api/sets/index's query: the numbers it reports and the shape it reports them in (de-ia6).

The shape is not a style preference.  The same four counts written as
correlated scalar subqueries over prod's 993 sets measured 21,460 ms against
39 ms for the aggregate-once-and-join form -- so `test_query_plan_has_no_correlated_subquery`
is the load-bearing test in this file.  It reads EXPLAIN QUERY PLAN rather than
a stopwatch because on a fixture-sized database both forms are instant, and a
timing assertion would go green over the regression it exists to catch.

To run: uv run pytest tests/test_set_index.py -v
"""

import sqlite3

import pytest

from mtg_collector.db.schema import init_db, rebuild_number_sortable
from mtg_collector.db.set_index import INDEX_SQL, set_index

#: fin as prod holds it: the base set ends at 309, the set has 599 printings.
FIN_BASE_SET_SIZE = 309
FIN_TOTAL_SET_SIZE = 599
#: ...but 311 printings sit at or below 309, because 123a/123b share a number.
#: A size is a boundary, not a count.
FIN_BASE_PRINTINGS = 311


def _seed_printings(conn, set_code, numbers):
    conn.executemany(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number)"
        " VALUES (?, 'oracle-1', ?, ?)",
        [(f"{set_code}-{cn}", set_code, cn) for cn in numbers],
    )


def _own(conn, printing_id, status="owned"):
    conn.execute(
        "INSERT INTO collection (printing_id, finish, acquired_at, source, status)"
        " VALUES (?, 'nonfoil', '2026-01-01T00:00:00.000Z', 'manual', ?)",
        (printing_id, status),
    )


@pytest.fixture
def db():
    """fin, a cached set with no booster config, a sizeless set, an uncached set.

    fin's printings are faithful to the *shape* the counting rule has to
    survive rather than to its actual card names: 309 plain base numbers, two
    suffixed numbers inside the base range, boosterfun above the boundary, and
    one Alchemy number whose CAST to INTEGER is 0.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO cards (oracle_id, name) VALUES ('oracle-1', 'Placeholder')")
    conn.executemany(
        "INSERT INTO sets (set_code, set_name, set_type, released_at, digital,"
        " cards_fetched_at, base_set_size, total_set_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("fin", "Final Fantasy", "expansion", "2025-06-13", 0,
             "2026-08-23T00:00:00Z", FIN_BASE_SET_SIZE, FIN_TOTAL_SET_SIZE),
            # Cached, no booster config, and no release date — three separate
            # ways a set falls out of a less careful query.
            ("spg", "Special Guests", "masterpiece", None, 0,
             "2026-08-23T00:00:00Z", 2, 2),
            ("nul", "Sizeless", "promo", "2024-01-01", 0,
             "2026-08-23T00:00:00Z", None, None),
            ("oth", "Not Cached", "expansion", "2026-01-01", 0, None, 100, 100),
        ],
    )

    base = [str(n) for n in range(1, FIN_BASE_SET_SIZE + 1)] + ["123a", "123b"]
    assert len(base) == FIN_BASE_PRINTINGS
    boosterfun = [str(n) for n in range(FIN_BASE_SET_SIZE + 1, 597)]
    _seed_printings(conn, "fin", base + boosterfun + ["A-248"])
    _seed_printings(conn, "spg", ["1", "2"])
    _seed_printings(conn, "nul", ["1", "2", "3"])
    _seed_printings(conn, "oth", ["1"])
    rebuild_number_sortable(conn)
    conn.commit()

    assert conn.execute(
        "SELECT COUNT(*) FROM printings WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_TOTAL_SET_SIZE

    yield conn
    conn.close()


def _by_code(rows):
    return {row["set_code"]: row for row in rows}


# ── Population: cached sets, all of them ──


def test_an_uncached_set_is_not_in_the_index(db):
    """`cards_fetched_at IS NULL` means no printings behind the row."""
    assert "oth" not in _by_code(set_index(db))


def test_a_set_with_no_booster_config_is_in_the_index(db):
    """The whole reason this is not /api/sets.

    `/api/sets` reads `mtgjson_booster_configs`, so Commander decks, Secret
    Lairs and every other set you cannot open a pack from are silently absent
    from it.  A binder holds those.
    """
    rows = _by_code(set_index(db))

    assert db.execute(
        "SELECT COUNT(*) FROM mtgjson_booster_configs WHERE set_code = 'spg'"
    ).fetchone()[0] == 0
    assert rows["spg"]["set_name"] == "Special Guests"
    assert rows["spg"]["total_all"] == 2


# ── The counts ──


def test_base_completion_counts_printings_not_the_boundary(db):
    """fin reads 309/311, never n/309 — two pockets would go missing."""
    _own(db, "fin-5")
    _own(db, "fin-123a")
    db.commit()

    fin = _by_code(set_index(db))["fin"]

    assert fin["base_set_size"] == FIN_BASE_SET_SIZE
    assert fin["total_base"] == FIN_BASE_PRINTINGS
    assert fin["total_base"] != FIN_BASE_SET_SIZE
    assert fin["owned_base"] == 2


def test_an_alchemy_number_is_not_in_the_base_set(db):
    """`CAST('A-248' AS INTEGER)` is 0, which is <= every boundary.

    Counting the base set with a CAST would file every Alchemy rebalance under
    it — the same bug in the same column that `number_sortable` was added to
    fix for ordering.
    """
    _own(db, "fin-A-248")
    db.commit()

    fin = _by_code(set_index(db))["fin"]

    assert fin["owned_all"] == 1
    assert fin["owned_base"] == 0


def test_totals_cover_every_section(db):
    fin = _by_code(set_index(db))["fin"]

    assert fin["total_all"] == FIN_TOTAL_SET_SIZE
    assert fin["owned_all"] == 0


def test_copies_of_one_printing_fill_one_pocket(db):
    """A pocket holds a printing; owning 28 of it does not fill 28 pockets."""
    for _ in range(3):
        _own(db, "fin-5")
    db.commit()

    fin = _by_code(set_index(db))["fin"]

    assert fin["owned_all"] == 1
    assert fin["owned_base"] == 1


def test_a_card_on_order_is_not_a_filled_pocket(db):
    _own(db, "fin-5", status="ordered")
    _own(db, "fin-6", status="sold")
    db.commit()

    fin = _by_code(set_index(db))["fin"]

    assert fin["owned_all"] == 0


def test_a_set_with_no_stored_boundary_reports_no_base_fraction(db):
    """NULL in, NULL out — 0/0 renders as NaN%, so the UI must be able to see it."""
    _own(db, "nul-1")
    db.commit()

    row = _by_code(set_index(db))["nul"]

    assert row["base_set_size"] is None
    assert row["owned_base"] is None
    assert row["total_base"] is None
    # The all-sections meter still works: every cached set has printings.
    assert (row["owned_all"], row["total_all"]) == (1, 3)


def test_a_cached_set_with_no_owned_cards_reads_zero_not_null(db):
    fin = _by_code(set_index(db))["fin"]

    assert fin["owned_all"] == 0
    assert fin["owned_base"] == 0


# ── Order and shape ──


def test_newest_release_first_and_undated_sets_last(db):
    """The client groups by set_type preserving first-appearance order, so this
    ordering is what makes the groups come out newest-first without a second sort."""
    codes = [row["set_code"] for row in set_index(db)]

    assert codes == ["fin", "nul", "spg"]


def test_row_carries_what_the_page_renders(db):
    fin = _by_code(set_index(db))["fin"]

    assert fin == {
        "set_code": "fin",
        "set_name": "Final Fantasy",
        "set_type": "expansion",
        "released_at": "2025-06-13",
        "digital": 0,
        "base_set_size": FIN_BASE_SET_SIZE,
        "total_set_size": FIN_TOTAL_SET_SIZE,
        "owned_base": 0,
        "total_base": FIN_BASE_PRINTINGS,
        "owned_all": 0,
        "total_all": FIN_TOTAL_SET_SIZE,
    }


# ── The shape that makes it 39 ms instead of 21.5 s ──


def _plan(conn):
    return "\n".join(row["detail"] for row in conn.execute("EXPLAIN QUERY PLAN " + INDEX_SQL))


def test_query_plan_has_no_correlated_subquery(db):
    """Aggregate once and join; never once per set.

    Asserted on the plan, not on the clock: at fixture scale the correlated
    form is instant too, so a timing budget would let this regress silently.
    Measured at prod scale it is 33,432 ms against 99.8 ms.
    """
    plan = _plan(db)

    assert "CORRELATED" not in plan.upper(), plan


def test_the_base_count_is_served_by_the_covering_index(db):
    """Worth 6.6x, and only because the base predicate sits in WHERE.

    Written as a conditional SUM over a plain GROUP BY, SQLite scans
    `idx_printings_set` — which does not carry `number_sortable` — and then
    fetches all 110,018 rows from a 616 MB table to read one integer: 662 ms
    against 59 ms. The app never runs ANALYZE, so no `sqlite_stat1` will
    correct that choice later.
    """
    plan = _plan(db)

    assert "SCAN p USING COVERING INDEX idx_printings_set_sortable" in plan, plan
