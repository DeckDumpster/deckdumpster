"""``_bulk_attach_prices`` binds a bounded number of parameters per statement.

Tier 1 -- no container, no network.  Runs the real helper against an in-memory
``latest_prices``.

Why this is worth pinning.  The helper built one ``IN (...)`` clause holding two
bound parameters per distinct card, so the SQL grew with whatever the caller
handed it.  That is the shape de-ckq removed from /api/collection, where 112,809
rows reached 225,618 parameters against a SQLITE_MAX_VARIABLE_NUMBER of 250,000;
it survived here because ``/api/sheets`` passes every distinct card across every
booster sheet of a product, bounded by nothing in the code.  Reality bounds it at
low four figures (779 for j25 jumpstart), so this closes the pattern rather than
an outage -- and a pattern only stays closed if something fails when it reopens.

The two assertions are separate on purpose: batching that loses a card in the
final partial batch would satisfy the bound and break the endpoint.
"""

import sqlite3

import pytest

from mtg_collector.cli.crack_pack_server import _PRICE_LOOKUP_BATCH, _bulk_attach_prices


class _CountingConn:
    """Passes execute() through, recording how many parameters each one bound."""

    def __init__(self, conn):
        self._conn = conn
        self.param_counts: list[int] = []

    def execute(self, sql, params=()):
        self.param_counts.append(len(params))
        return self._conn.execute(sql, params)


@pytest.fixture
def priced_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE latest_prices (
               set_code TEXT, collector_number TEXT, source TEXT,
               price_type TEXT, price REAL,
               PRIMARY KEY (set_code, collector_number, source, price_type))"""
    )
    return conn


def _cards(n, set_code="tst"):
    return [{"set_code": set_code, "collector_number": str(i), "foil": False} for i in range(n)]


def _price_rows(cards, tcg):
    return [(c["set_code"], c["collector_number"], "tcgplayer", "normal", tcg) for c in cards]


# One under a batch, exactly a batch, and a batch and a bit -- the boundary and
# both sides of it.  4x a batch is the multi-statement case.
@pytest.mark.parametrize(
    "count",
    [
        1,
        _PRICE_LOOKUP_BATCH - 1,
        _PRICE_LOOKUP_BATCH,
        _PRICE_LOOKUP_BATCH + 1,
        _PRICE_LOOKUP_BATCH * 4 + 7,
    ],
)
def test_no_statement_binds_more_than_one_batch(priced_conn, count):
    cards = _cards(count)
    priced_conn.executemany(
        "INSERT INTO latest_prices VALUES (?,?,?,?,?)", _price_rows(cards, 1.5)
    )
    counting = _CountingConn(priced_conn)

    _bulk_attach_prices(counting, cards)

    assert counting.param_counts, "no query was issued"
    assert max(counting.param_counts) <= 2 * _PRICE_LOOKUP_BATCH


@pytest.mark.parametrize("count", [_PRICE_LOOKUP_BATCH + 1, _PRICE_LOOKUP_BATCH * 4 + 7])
def test_every_card_across_every_batch_is_priced(priced_conn, count):
    """Including the ones in the final, partial batch."""
    cards = _cards(count)
    priced_conn.executemany(
        "INSERT INTO latest_prices VALUES (?,?,?,?,?)", _price_rows(cards, 2.25)
    )

    _bulk_attach_prices(priced_conn, cards)

    assert [c["tcg_price"] for c in cards] == ["2.25"] * count


def test_a_card_with_no_price_row_gets_none(priced_conn):
    """The batching must not turn a missing price into a neighbour's price."""
    cards = _cards(_PRICE_LOOKUP_BATCH + 3)
    priced_conn.executemany(
        "INSERT INTO latest_prices VALUES (?,?,?,?,?)", _price_rows(cards[:-1], 3.0)
    )

    _bulk_attach_prices(priced_conn, cards)

    assert cards[-1]["tcg_price"] is None
    assert cards[-1]["ck_price"] is None
    assert cards[-2]["tcg_price"] == "3.0"
