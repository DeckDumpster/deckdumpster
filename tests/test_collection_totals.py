"""
Whole-result figures and price sorting on /api/collection.

The client fetches windows as it scrolls, so the rows it holds are a growing
prefix of the result rather than the result.  Two things have to come from the
server for that to work:

  * `total_qty` / `total_value`, because a status line summed from the rows in
    memory would climb as the user scrolled.
  * an ordering for every sortable column, because sorting in the browser would
    order the loaded rows against each other and leave the rest of the result in
    the previous query's order.

To run: uv run pytest tests/test_collection_totals.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.schema import init_db, refresh_latest_prices

NOW = "2025-01-01T00:00:00.000Z"


def _add_card(conn, n, name):
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors, color_identity) "
        "VALUES (?, ?, '{R}', 'Creature', '[\"R\"]', '[\"R\"]')",
        (f"oracle-{n}", name),
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes) "
        "VALUES (?, ?, 'tst', ?, 'R', '[\"nonfoil\", \"foil\"]')",
        (f"print-{n}", f"oracle-{n}", str(n)),
    )


def _own(conn, n, finish, copies):
    for _ in range(copies):
        conn.execute(
            "INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
            "VALUES (?, ?, ?, 'manual', 'owned')",
            (f"print-{n}", finish, NOW),
        )


def _price(conn, cn, source, price_type, price):
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('tst', ?, ?, ?, ?, '2025-01-01')",
        (str(cn), source, price_type, price),
    )


# Four groups, 7 copies.  Quantities differ from row counts on purpose: a
# total_qty that merely counted rows would read 4 and pass a weaker test.
#
# The two price sources rank the cards differently (Alpha is the cheapest by
# TCG and the dearest by CK), so a test that sorts or sums by one cannot pass
# while silently using the other.
#
#   printing  copies  finish   tcg    ck buylist   tcg value   ck value
#   1         3       nonfoil  2.00   6.00          6.00       18.00
#   2         1       nonfoil  10.00  4.00         10.00        4.00
#   3         2       foil      5.00  3.00         10.00        6.00
#   4         1       nonfoil   —      —             0.00        0.00
TOTAL_ROWS = 4
TOTAL_QTY = 7
TOTAL_VALUE_TCG = 26.00
TOTAL_VALUE_CK = 28.00
# Ascending. NULL sorts first in SQLite, so the unpriced card leads both.
ORDER_BY_TCG = ["Delta", "Alpha", "Charlie", "Bravo"]
ORDER_BY_CK = ["Delta", "Charlie", "Bravo", "Alpha"]


@pytest.fixture
def priced_db():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")

    _add_card(conn, 1, "Alpha")
    _own(conn, 1, "nonfoil", 3)
    _price(conn, 1, "tcgplayer", "normal", 2.0)
    _price(conn, 1, "cardkingdom", "buylist_normal", 6.0)

    _add_card(conn, 2, "Bravo")
    _own(conn, 2, "nonfoil", 1)
    _price(conn, 2, "tcgplayer", "normal", 10.0)
    _price(conn, 2, "cardkingdom", "buylist_normal", 4.0)

    _add_card(conn, 3, "Charlie")
    _own(conn, 3, "foil", 2)
    _price(conn, 3, "tcgplayer", "foil", 5.0)
    _price(conn, 3, "cardkingdom", "buylist_foil", 3.0)
    _price(conn, 3, "tcgplayer", "normal", 999.0)  # wrong finish, must not count

    _add_card(conn, 4, "Delta")
    _own(conn, 4, "nonfoil", 1)

    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _set_price_source(db_path, value):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET value = ? WHERE key = 'price_sources'", (value,))
    conn.commit()
    conn.close()


def _page(db_path, **params):
    """Call /api/collection and return the whole envelope."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()  # truthy, never called by this path
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))
    handler._api_collection({k: [str(v)] for k, v in params.items()})
    status, body = responses[-1]
    assert status == 200, body
    return body


class TestWholeResultTotals:
    """The figures describe the result, not the page."""

    def test_full_result_in_one_page(self, priced_db):
        body = _page(priced_db)
        assert body["total"] == TOTAL_ROWS
        assert body["total_qty"] == TOTAL_QTY
        assert body["total_value"] == TOTAL_VALUE_TCG

    @pytest.mark.parametrize("limit", [1, 2, 3])
    def test_a_page_does_not_shrink_the_totals(self, priced_db, limit):
        """The reason this exists: a status line summed from the page would
        report a fraction of the collection and grow as the user scrolled."""
        body = _page(priced_db, limit=limit)
        assert len(body["rows"]) == limit
        assert body["total"] == TOTAL_ROWS
        assert body["total_qty"] == TOTAL_QTY
        assert body["total_value"] == TOTAL_VALUE_TCG

    def test_totals_hold_while_walking_the_result(self, priced_db):
        """The line does not move as pages arrive.

        The first window carries the totals; later windows carry none, so the
        client keeps the figures it already has (de-962 — recomputing them per
        window cost 1.0 s of the 1.5 s a scroll fetch took).  What must never
        happen is a *different* value arriving later and moving the line, so
        this asserts absence, not a stale repeat.

        `total` stays on every window: deck-builder.js pages its card picker
        until `offset >= total`.
        """
        first = _page(priced_db, limit=1, offset=0)
        assert (first["total"], first["total_qty"], first["total_value"]) == (
            TOTAL_ROWS,
            TOTAL_QTY,
            TOTAL_VALUE_TCG,
        )

        for offset in range(1, TOTAL_ROWS + 1):
            body = _page(priced_db, limit=1, offset=offset)
            assert body["total"] == TOTAL_ROWS, offset
            assert "total_qty" not in body, offset
            assert "total_value" not in body, offset

    def test_short_page_and_counted_page_agree(self, priced_db):
        """A page that holds the whole result is summed from the rows in hand;
        a bounded one is summed in SQL.  The two paths must not disagree."""
        whole = _page(priced_db, limit=TOTAL_ROWS + 1)
        bounded = _page(priced_db, limit=1)
        assert (whole["total_qty"], whole["total_value"]) == (
            bounded["total_qty"],
            bounded["total_value"],
        )

    def test_value_follows_the_configured_price_source(self, priced_db):
        """The status line sits beside the price column, so it prices the
        collection the same way."""
        _set_price_source(priced_db, "ck,tcg")
        for limit in (1, TOTAL_ROWS + 1):  # both the SQL and the in-hand path
            assert _page(priced_db, limit=limit)["total_value"] == TOTAL_VALUE_CK

    def test_query_narrows_the_totals(self, priced_db):
        body = _page(priced_db, q="Alpha")
        assert (body["total"], body["total_qty"], body["total_value"]) == (1, 3, 6.0)

    def test_empty_result(self, priced_db):
        body = _page(priced_db, q="Nonexistent")
        assert (body["total"], body["total_qty"], body["total_value"]) == (0, 0, 0)


class TestPriceSorting:
    """tcg_price and ck_price are offered as sortable columns by the collection
    table.  Before windowing they were sorted in the browser; over pages that
    would only order the rows already loaded."""

    def _walk(self, db_path, sort, order="asc", limit=1):
        names = []
        offset = 0
        while True:
            body = _page(db_path, sort=sort, order=order, limit=limit, offset=offset)
            if not body["rows"]:
                return names
            names.extend(r["name"] for r in body["rows"])
            offset += len(body["rows"])

    def test_sort_by_tcg_price(self, priced_db):
        assert self._walk(priced_db, "tcg_price") == ORDER_BY_TCG

    def test_sort_by_tcg_price_desc(self, priced_db):
        assert self._walk(priced_db, "tcg_price", order="desc") == ORDER_BY_TCG[::-1]

    def test_sort_by_ck_price(self, priced_db):
        """The two sources rank the cards differently, so this cannot pass by
        sorting on the other price — or by falling back to the default sort."""
        assert self._walk(priced_db, "ck_price") == ORDER_BY_CK
        assert ORDER_BY_CK != ORDER_BY_TCG

    def test_price_sorted_walk_has_no_gaps_or_repeats(self, priced_db):
        """Paging a non-total order silently drops and duplicates rows, so the
        tiebreak has to hold under a sort whose column repeats."""
        walked = self._walk(priced_db, "tcg_price", limit=1)
        assert sorted(walked) == ["Alpha", "Bravo", "Charlie", "Delta"]

    def test_page_size_does_not_change_the_order(self, priced_db):
        """The window the client happens to ask for cannot change what is in
        it — that is what makes scrolling equivalent to one long list."""
        for limit in (2, 3, 4):
            assert self._walk(priced_db, "tcg_price", limit=limit) == self._walk(
                priced_db, "tcg_price", limit=1
            )


class TestPriceSortDoesNotDuplicateRows:
    """`sort=price` must not multiply rows.

    latest_prices is keyed (set_code, collector_number, source, price_type), so
    a card with both a TCG and a Card Kingdom price at the same price_type has
    two rows there.  A sort join that pins only price_type matches both.  The
    GROUP BY templates collapse the duplicate — while leaving which source you
    sorted by undecided — but expand=copies has no GROUP BY, and paging a
    result whose rows are duplicated drops and repeats cards.

    Nothing sent `sort` until the client began fetching windows, so this was
    unreachable rather than absent.
    """

    @pytest.fixture
    def two_source_db(self, priced_db):
        """Give every card a Card Kingdom *retail* price alongside its TCG one,
        at the same price_type — the shape that makes a source-blind join
        match twice."""
        conn = sqlite3.connect(priced_db)
        for cn, price in ((1, 1.5), (2, 2.5), (3, 3.5)):
            _price(conn, cn, "cardkingdom", "normal", price)
            _price(conn, cn, "cardkingdom", "foil", price)
        refresh_latest_prices(conn)
        conn.commit()
        conn.close()
        return priced_db

    def test_fixture_really_has_two_sources(self, two_source_db):
        """Guard the guard: if this stops holding, the tests below pass for the
        wrong reason."""
        conn = sqlite3.connect(two_source_db)
        worst = conn.execute(
            "SELECT MAX(n) FROM (SELECT COUNT(DISTINCT source) n FROM latest_prices "
            "GROUP BY set_code, collector_number, price_type)"
        ).fetchone()[0]
        conn.close()
        assert worst > 1, "fixture no longer has one price_type served by two sources"

    @pytest.mark.parametrize("sort", ["price", "tcg_price", "ck_price"])
    def test_expand_copies_page_is_not_multiplied(self, two_source_db, sort):
        body = _page(two_source_db, expand="copies", sort=sort)
        ids = [r["collection_id"] for r in body["rows"]]
        assert len(ids) == len(set(ids)), f"sort={sort} duplicated rows: {ids}"
        assert len(ids) == TOTAL_QTY == body["total"]

    @pytest.mark.parametrize("sort", ["price", "tcg_price", "ck_price"])
    def test_offset_walk_covers_each_copy_once(self, two_source_db, sort):
        """The property paging actually depends on."""
        seen = []
        offset = 0
        while True:
            body = _page(two_source_db, expand="copies", sort=sort, limit=2, offset=offset)
            if not body["rows"]:
                break
            seen.extend(r["collection_id"] for r in body["rows"])
            offset += len(body["rows"])
            if offset >= body["total"]:
                break
        assert sorted(seen) == sorted(set(seen)), f"sort={sort} repeated copies while paging"
        assert len(seen) == TOTAL_QTY

    def test_price_sort_follows_the_displayed_source(self, two_source_db):
        """Sorting by the Price column must order by the number that column
        shows, not by whichever source the join happened to reach first."""
        _set_price_source(two_source_db, "ck,tcg")
        by_price = [r["name"] for r in _page(two_source_db, sort="price")["rows"]]
        by_ck = [r["name"] for r in _page(two_source_db, sort="ck_price")["rows"]]
        assert by_price == by_ck


# --- The LEFT-JOIN template: rows that have no copy -------------------------
#
# `is:unowned` (and the shared-links `cards=` list) LEFT JOIN `collection`, so a
# result row can be a card nobody owns: qty 0, and therefore 0 towards
# total_value whatever that printing is priced at.  The sums are taken over a
# body that inner-joins the copies for exactly that reason — pricing 109,976
# copy-less rows to add zero was 6.6 s of a 7.3 s first paint (de-dfb).
#
# What that must not cost: `total` counts result rows, copy-less ones included,
# so it cannot come from the same body.  These pin both halves.

UNOWNED_PRICE = 100.0  # dear on purpose: a sum that reached it would be obvious


@pytest.fixture
def mixed_db():
    """One owned printing and one owned by nobody, both priced."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")

    _add_card(conn, 1, "Alpha")
    _own(conn, 1, "nonfoil", 3)
    _price(conn, 1, "tcgplayer", "normal", 2.0)

    _add_card(conn, 5, "Echo")  # no copies
    _price(conn, 5, "tcgplayer", "normal", UNOWNED_PRICE)

    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _recorded(db_path, **params):
    """Call /api/collection, returning (envelope, statements it ran)."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    statements = []

    class _Recording:
        def __init__(self, path):
            self._conn = sqlite3.connect(path)
            self._conn.row_factory = sqlite3.Row

        def execute(self, sql, sql_params=()):
            statements.append((sql, list(sql_params)))
            return self._conn.execute(sql, sql_params)

        def close(self):
            pass  # the test reads the plans after the handler is done

    rec = _Recording(db_path)
    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()
    handler._get_conn = lambda: rec
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))
    handler._api_collection({k: [str(v)] for k, v in params.items()})
    status, body = responses[-1]
    assert status == 200, body
    return body, rec, statements


class TestRowsWithNoCopy:
    def test_unowned_result_is_worth_nothing(self, mixed_db):
        """One row, priced at $100, owned by nobody.  It is worth $0."""
        body = _page(mixed_db, q="is:unowned", limit=1)
        assert body["total"] == 1
        assert body["total_qty"] == 0
        assert body["total_value"] == 0

    def test_total_counts_rows_the_sums_skip(self, mixed_db):
        """The regression the split has to survive.

        A shared-links list is the same LEFT-JOIN template holding one owned
        card and one unowned one.  `total` is 2 — deck-builder.js pages until
        `offset >= total`, so a total taken from the copies-only body would
        stop it a card early — while the sums see only the copies.
        """
        body = _page(mixed_db, cards="tst:1,tst:5", limit=1)
        assert body["total"] == 2
        assert body["total_qty"] == 3
        assert body["total_value"] == 6.00

    def test_the_two_templates_agree_on_the_same_card(self, mixed_db):
        """Alpha is worth the same whichever template found it."""
        left_join = _page(mixed_db, cards="tst:1", limit=1)
        default = _page(mixed_db, q="Alpha", limit=1)
        assert (left_join["total_qty"], left_join["total_value"]) == (
            default["total_qty"],
            default["total_value"],
        )

    def test_the_sums_do_not_walk_the_copyless_rows(self, mixed_db):
        """Pin the mechanism, not just the answer.

        The sums must reach `collection` through an inner join, so the price
        joins are never reached for a row with no copy.  A LEFT-JOIN step here
        means the whole result is being priced again.
        """
        _, rec, statements = _recorded(mixed_db, q="is:unowned", limit=1)
        sums = [(sql, p) for sql, p in statements if "SUM(qty * price)" in sql]
        assert len(sums) == 1, f"expected one totals statement, got {len(sums)}"
        sql, sql_params = sums[0]
        assert "COUNT(*)" not in sql, (
            "the count is riding on the totals body, which no longer spans the "
            "result:\n" + sql
        )
        plan = [r[3] for r in rec.execute(f"EXPLAIN QUERY PLAN {sql}", sql_params)]
        rec._conn.close()
        offending = [s for s in plan if s.startswith("SEARCH c ") and "LEFT-JOIN" in s]
        assert not offending, (
            "the totals are still walking rows with no copy:\n  " + "\n  ".join(plan)
        )

    def test_the_owned_templates_still_count_and_sum_in_one_scan(self, priced_db):
        """The split is scoped to the template that needs it.

        Where the totals body already drives from `collection` it has a row per
        result row, so one scan answers all three — 792 ms against 1,242 ms
        split, on 15,045 copies.
        """
        _, rec, statements = _recorded(priced_db, limit=1)
        rec._conn.close()
        combined = [sql for sql, _ in statements if "SUM(qty * price)" in sql]
        assert len(combined) == 1
        assert "COUNT(*)" in combined[0], combined[0]
        assert not [sql for sql, _ in statements if sql.startswith("SELECT COUNT(*) FROM (SELECT 1")]
