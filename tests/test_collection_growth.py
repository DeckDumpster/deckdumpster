"""
The growth chart's two routes to the same numbers (de-tz9).

`/api/collection/growth` reads the unfiltered series out of the materialized
`collection_value_history` table and computes everything else from `collection`
+ `prices`.  Two routes to one answer is a licence to disagree, so these tests
are mostly about the ways the stored one could be wrong:

  * it must equal the computed one, point for point, before anything moves;
  * it must stop being used the moment the collection or the prices move under
    it — the failure mode of a cache is not slowness, it is a confident wrong
    number;
  * a filtered request must never touch it, because it describes a population
    the filter has already excluded rows from.

To run: uv run pytest tests/test_collection_growth.py -v
"""

import datetime as dt
import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db import growth
from mtg_collector.db.schema import init_db, refresh_latest_prices


def _day(offset: int) -> str:
    """A UTC date `offset` days from today, as the collection stores dates."""
    return (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=offset)).isoformat()


def _stamp(offset: int) -> str:
    return f"{_day(offset)}T12:00:00.000Z"


def _add_card(conn, n, name, set_code="tst"):
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors, color_identity) "
        "VALUES (?, ?, '{R}', 'Creature — Goblin', '[\"R\"]', '[\"R\"]')",
        (f"oracle-{n}", name),
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes) "
        "VALUES (?, ?, ?, ?, 'R', '[\"nonfoil\", \"foil\"]')",
        (f"print-{n}", f"oracle-{n}", set_code, str(n)),
    )


def _own(conn, n, acquired_offset, copies=1, finish="nonfoil", status="owned"):
    for _ in range(copies):
        conn.execute(
            "INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
            "VALUES (?, ?, ?, 'manual', ?)",
            (f"print-{n}", finish, _stamp(acquired_offset), status),
        )


def _price(conn, n, offset, tcg=None, ck=None, price_type="normal", set_code="tst"):
    for source, value in (("tcgplayer", tcg), ("cardkingdom", ck)):
        if value is None:
            continue
        conn.execute(
            "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (set_code, str(n), source, price_type, value, _day(offset)),
        )


def _log_price_fetch(conn):
    """Record a price import the way `import_prices` does."""
    conn.execute(
        "INSERT INTO price_fetch_log (fetched_at, source_file, dates_imported,"
        " uuid_total, uuid_mapped, uuid_unmapped, rows_inserted)"
        " VALUES (?, 'test', '[]', 0, 0, 0, 0)",
        (_stamp(0),),
    )


# Three cards, acquired on different days, priced on different days, so the
# series has to move for more than one reason:
#
#   card  copies  acquired   tcg on -10 / -4      ck on -10 / -4
#   1     2       -10 days   1.00      3.00       0.50      0.50
#   2     1        -4 days   —        10.00       —         2.00
#   3     1        -4 days   (never priced: counts, contributes nothing)
@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")

    _add_card(conn, 1, "Alpha")
    _own(conn, 1, -10, copies=2)
    _price(conn, 1, -10, tcg=1.00, ck=0.50)
    _price(conn, 1, -4, tcg=3.00, ck=0.50)

    _add_card(conn, 2, "Bravo")
    _own(conn, 2, -4)
    _price(conn, 2, -4, tcg=10.00, ck=2.00)

    _add_card(conn, 3, "Charlie")
    _own(conn, 3, -4)

    _log_price_fetch(conn)
    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _growth(db_path, **params):
    """Call /api/collection/growth and return the response body."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()  # truthy, never called by this path
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))
    handler._api_collection_growth({k: [str(v)] for k, v in params.items()})
    status, body = responses[-1]
    assert status == 200, body
    return body


def _set_price_source(db_path, value):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE settings SET value = ? WHERE key = 'price_sources'", (value,))
    conn.commit()
    conn.close()


def _computed(conn, **kwargs):
    kwargs.setdefault("where_sql", growth.UNFILTERED_WHERE)
    kwargs.setdefault("params", [])
    return growth.compute_series(conn, **kwargs)


class TestTheTwoRoutesAgree:
    """The materialized series is the computed one, or it is a bug."""

    def test_unfiltered_matches_the_computed_series(self, db_path, conn):
        assert _growth(db_path) == _computed(conn)

    def test_the_numbers_are_the_ones_arithmetic_gives(self, db_path):
        """Pinned by hand, so an error shared by both routes still fails.

        Two Alphas at 1.00 from day -10, joined on day -4 by a second Alpha
        price, a Bravo and an unpriced Charlie.
        """
        body = _growth(db_path)
        by_day = dict(zip(body["dates"], body["counts"]))
        assert by_day[_day(-10)] == 2
        assert by_day[_day(-5)] == 2
        assert by_day[_day(-4)] == 4
        assert by_day[_day(0)] == 4

        tcg = dict(zip(body["dates"], body["tcg_values"]))
        assert tcg[_day(-10)] == 2.00   # 2 x 1.00
        assert tcg[_day(-5)] == 2.00    # forward-filled
        assert tcg[_day(-4)] == 16.00   # 2 x 3.00 + 10.00 + unpriced Charlie
        assert tcg[_day(0)] == 16.00

        ck = dict(zip(body["dates"], body["ck_values"]))
        assert ck[_day(-10)] == 1.00
        assert ck[_day(-4)] == 3.00

        assert body["earliest"] == _day(-10)

    @pytest.mark.parametrize("range_days", [1, 3, 7, 30, 3650])
    def test_a_window_is_a_slice_of_the_full_series(self, db_path, range_days):
        """The stored table holds full history and serves windows by slicing;
        that is only sound because every point is absolute."""
        full = _growth(db_path)
        windowed = _growth(db_path, range=range_days)
        n = len(windowed["dates"])
        assert n > 0
        for key in ("dates", "counts", "tcg_values", "ck_values"):
            assert windowed[key] == full[key][-n:], key
        assert windowed["earliest"] == full["earliest"]

    def test_windows_agree_with_the_computed_route(self, db_path, conn):
        assert _growth(db_path, range=5) == _computed(conn, range_days=5)


class TestStaleness:
    """What must invalidate the stored series, and what must not."""

    def test_a_new_card_is_visible_immediately(self, db_path, conn):
        """The failure this guards: a card added after the last rebuild is
        simply absent from the chart until the next 06:00 price fetch."""
        before = _growth(db_path)  # materializes
        conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('two', 'Other')")
        _add_card(conn, 9, "Delta", set_code="two")
        _own(conn, 9, -6, copies=3)
        conn.commit()

        after = _growth(db_path)
        assert after != before
        assert after == _computed(conn)
        assert after["counts"][-1] == before["counts"][-1] + 3

    def test_a_backdated_card_rewrites_history(self, db_path, conn):
        """A card acquired before the series starts moves `earliest` and every
        point after it — the stored table cannot be patched, only rebuilt."""
        before = _growth(db_path)
        conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('two', 'Other')")
        _add_card(conn, 9, "Delta", set_code="two")
        _own(conn, 9, -40)
        conn.commit()

        after = _growth(db_path)
        assert after["earliest"] == _day(-40)
        assert before["earliest"] == _day(-10)
        assert after == _computed(conn)

    def test_selling_a_card_leaves_the_series(self, db_path, conn):
        before = _growth(db_path)
        conn.execute("UPDATE collection SET status = 'sold' WHERE printing_id = 'print-2'")
        conn.commit()

        after = _growth(db_path)
        assert after["counts"][-1] == before["counts"][-1] - 1
        assert after == _computed(conn)

    def test_refinishing_a_card_reprices_it(self, db_path, conn):
        """finish decides which price series a card is valued from, so it
        changes the answer without changing the count."""
        _price(conn, 1, -4, tcg=99.00, price_type="foil")
        conn.commit()
        before = _growth(db_path)

        conn.execute("UPDATE collection SET finish = 'foil' WHERE printing_id = 'print-1'")
        conn.commit()

        after = _growth(db_path)
        assert after["counts"] == before["counts"]
        assert after["tcg_values"][-1] != before["tcg_values"][-1]
        assert after == _computed(conn)

    def test_new_prices_are_visible_immediately(self, db_path, conn):
        """A price import is the other thing that moves the series, and it
        moves days already stored, not just today's."""
        before = _growth(db_path)
        _price(conn, 2, -2, tcg=50.00)
        _log_price_fetch(conn)
        conn.commit()

        after = _growth(db_path)
        assert after["tcg_values"][-1] == before["tcg_values"][-1] + 40.00
        assert after == _computed(conn)

    def test_an_unrelated_edit_keeps_the_stored_series(self, db_path, conn):
        """Notes and binder assignments are not in the series, so editing one
        must not throw away a perfectly good build."""
        _growth(db_path)
        built_at = conn.execute(
            "SELECT built_at FROM collection_value_history_meta"
        ).fetchone()[0]

        conn.execute("UPDATE collection SET notes = 'foo' WHERE id = 1")
        conn.commit()
        assert growth.history_is_current(conn)

        _growth(db_path)
        assert conn.execute(
            "SELECT built_at FROM collection_value_history_meta"
        ).fetchone()[0] == built_at

    def test_a_valid_build_is_reused(self, db_path, conn):
        """The point of the exercise: the second request does not rebuild."""
        _growth(db_path)
        assert growth.history_is_current(conn)

        conn.execute("UPDATE collection_value_history SET n = -1")
        conn.commit()
        # Read straight out of the table, sabotage included — proof the second
        # request never recomputed.
        assert set(_growth(db_path)["counts"]) == {-1}


class TestTriggers:
    """The revision stamp the staleness check rests on."""

    def test_insert_update_and_delete_all_bump_the_stamp(self, conn):
        seen = [growth.collection_rev(conn)]
        _own(conn, 1, -1)
        seen.append(growth.collection_rev(conn))
        conn.execute("UPDATE collection SET status = 'sold' WHERE id = 1")
        seen.append(growth.collection_rev(conn))
        conn.execute("DELETE FROM collection WHERE id = 1")
        seen.append(growth.collection_rev(conn))
        assert seen == sorted(set(seen)), seen

    def test_columns_outside_the_series_do_not_bump_it(self, conn):
        before = growth.collection_rev(conn)
        conn.execute("UPDATE collection SET notes = 'x', condition = 'Damaged'")
        conn.execute("UPDATE collection SET binder_id = NULL")
        assert growth.collection_rev(conn) == before

    def test_a_missing_stamp_is_an_error_not_a_shrug(self, conn):
        """Serving the chart off a stamp that cannot move is exactly the silent
        wrong answer this whole mechanism exists to prevent."""
        conn.execute("DELETE FROM collection_rev")
        with pytest.raises(RuntimeError, match="mtg db init --force"):
            growth.collection_rev(conn)


class TestFilteredRequestsGoTheOtherWay:
    """A filter selects a different population; the stored table is not it."""

    def test_a_filter_narrows_the_series(self, db_path, conn):
        body = _growth(db_path, q="Alpha")
        assert body["counts"][-1] == 2
        assert body["tcg_values"][-1] == 6.00
        assert body["earliest"] == _day(-10)

    def test_a_filter_does_not_read_the_stored_table(self, db_path, conn):
        """Sabotage the table, then filter: a filtered answer that changed
        would mean the fast path leaked into a query it cannot serve."""
        _growth(db_path)
        conn.execute("UPDATE collection_value_history SET n = -1, tcg_cents = -1")
        conn.commit()

        body = _growth(db_path, q="Alpha")
        assert body["counts"][-1] == 2
        assert body["tcg_values"][-1] == 6.00

    def test_a_filter_does_not_write_the_stored_table(self, db_path, conn):
        """...and it does not overwrite the unfiltered build with its own,
        narrower numbers."""
        unfiltered = _growth(db_path)
        _growth(db_path, q="Alpha")
        assert _growth(db_path) == unfiltered

    def test_a_status_filter_still_computes(self, db_path, conn):
        conn.execute("UPDATE collection SET status = 'sold' WHERE printing_id = 'print-2'")
        conn.commit()
        body = _growth(db_path, q="status:sold")
        assert body["counts"][-1] == 1

    def test_blank_query_is_the_unfiltered_case(self, db_path):
        """A query bar holding whitespace is what an empty one posts."""
        assert _growth(db_path, q="   ") == _growth(db_path)

    def test_is_unowned_is_empty(self, db_path):
        assert _growth(db_path, q="is:unowned") == growth.EMPTY_SERIES


class TestThePriceFilterIsTheDisplayedPrice:
    """`price:` selects the same cards here as on the collection page.

    Both reach `latest_prices`, whose key is (set_code, collector_number,
    source, price_type).  A join that pins neither source nor the copy's finish
    filters on whatever price any source happened to publish for any finish,
    so the same query bar described a different collection above the chart than
    beside it (de-fb1).
    """

    def test_the_filter_follows_the_configured_source(self, db_path, conn):
        """Bravo is 10.00 by TCG and 2.00 by Card Kingdom, so `price>5` cannot
        mean the same thing under both settings — and reading the source the
        chart is not drawn from is exactly the bug."""
        assert _growth(db_path, q="price>5")["counts"][-1] == 1

        _set_price_source(db_path, "ck,tcg")
        assert _growth(db_path, q="price>5") == growth.EMPTY_SERIES

    def test_the_filter_prices_a_copy_by_its_finish(self, db_path, conn):
        """A foil copy is worth its foil price; the series already values it
        that way, so the filter that decides whether it is in the series has to
        agree."""
        _own(conn, 1, -4, finish="foil")
        _price(conn, 1, -4, tcg=20.00, price_type="foil")
        _log_price_fetch(conn)
        refresh_latest_prices(conn)
        conn.commit()

        # The foil Alpha at 20.00 and Bravo at 10.00. The two nonfoil Alphas
        # are 3.00 and stay out.
        assert _growth(db_path, q="price>5")["counts"][-1] == 2


class TestEmptyCollection:
    def test_empty_collection_returns_the_empty_series(self, db_path, conn):
        conn.execute("DELETE FROM collection")
        conn.commit()
        assert _growth(db_path) == growth.EMPTY_SERIES

    def test_an_empty_build_does_not_age_out(self, db_path, conn):
        """There is no day axis to fall behind, so only a collection change can
        make "nothing" the wrong answer."""
        conn.execute("DELETE FROM collection")
        conn.commit()
        _growth(db_path)
        assert growth.history_is_current(conn)

    def test_the_first_card_after_an_empty_build_shows_up(self, db_path, conn):
        conn.execute("DELETE FROM collection")
        conn.commit()
        assert _growth(db_path) == growth.EMPTY_SERIES

        _own(conn, 1, -3, copies=2)
        conn.commit()
        body = _growth(db_path)
        assert body["earliest"] == _day(-3)
        assert body["counts"][-1] == 2


class TestRebuildHistory:
    """What the price timer calls."""

    def test_rebuild_stores_every_day_and_validates(self, db_path, conn):
        days = growth.rebuild_history(conn)
        assert days == len(_computed(conn)["dates"])
        assert conn.execute(
            "SELECT COUNT(*) FROM collection_value_history"
        ).fetchone()[0] == days
        assert growth.history_is_current(conn)

    def test_a_warmed_table_is_what_the_request_serves(self, db_path, conn):
        """The timer's job: the first chart of the day costs a table read."""
        growth.rebuild_history(conn)
        conn.execute("UPDATE collection_value_history SET n = -1")
        conn.commit()
        assert set(_growth(db_path)["counts"]) == {-1}

    def test_rebuild_is_idempotent(self, db_path, conn):
        growth.rebuild_history(conn)
        first = _growth(db_path)
        growth.rebuild_history(conn)
        assert _growth(db_path) == first

    def test_rebuild_leaves_no_staging_tables_behind(self, conn):
        """The timer reuses one process-wide connection, so a leftover TEMP
        table would collide on the next run rather than being dropped with the
        request's connection."""
        growth.rebuild_history(conn)
        growth.rebuild_history(conn)
        names = {
            r[0] for r in conn.execute("SELECT name FROM temp.sqlite_master")
        }
        assert names & {"pop_t", "keys_t", "seg_t"} == set()
