"""
Price and Card Kingdom URL enrichment on /api/decks/:id/cards.

This endpoint carried its own copy of the two follow-up passes that de-ckq
removed from /api/collection — an `IN (...)` over latest_prices and another
over mtgjson_printings, each sized by the deck.  It now reads the same joins
(mtg_collector/db/enrich.py) the collection list does.

The values are what these tests pin, because two of them moved:

  * a *copy* is priced in the finish it was recorded in, so a foil copy of a
    printing that also exists in nonfoil no longer shows the nonfoil price;
  * a double-faced card resolves to the same mtgjson row the collection list
    and the card detail page resolve, so the three pages link one card to one
    product.

An *expected* card — an idea deck's wishlist, where you may hold no copy at
all — has no finish to read, so it is priced on the printing instead.

To run: uv run pytest tests/test_deck_enrichment.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.schema import init_db, refresh_latest_prices

NOW = "2025-01-01T00:00:00.000Z"


def _add_card(conn, n, name, finishes='["nonfoil", "foil"]'):
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors, color_identity) "
        "VALUES (?, ?, '{R}', 'Creature', '[\"R\"]', '[\"R\"]')",
        (f"oracle-{n}", name),
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes) "
        "VALUES (?, ?, 'tst', ?, 'R', ?)",
        (f"print-{n}", f"oracle-{n}", str(n), finishes),
    )
    return f"print-{n}"


def _own(conn, n, finish):
    cur = conn.execute(
        "INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
        "VALUES (?, ?, ?, 'manual', 'owned')",
        (f"print-{n}", finish, NOW),
    )
    return cur.lastrowid


def _price(conn, cn, source, price_type, price):
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('tst', ?, ?, ?, ?, '2025-01-01')",
        (str(cn), source, price_type, price),
    )


def _mtgjson(conn, n, ck_url, ck_url_foil, uuid_suffix=""):
    conn.execute(
        "INSERT INTO mtgjson_printings (uuid, printing_id, name, set_code, number, ck_url, ck_url_foil, imported_at) "
        "VALUES (?, ?, 'x', 'tst', ?, ?, ?, '2025-01-01')",
        (f"uuid-{n}{uuid_suffix}", f"print-{n}", str(n), ck_url, ck_url_foil),
    )


def _deck(conn, name, state_id):
    cur = conn.execute(
        "INSERT INTO decks (name, state_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name, state_id, NOW, NOW),
    )
    return cur.lastrowid


@pytest.fixture
def deck_db():
    """A constructed deck and an idea deck over the same printings."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")

    # 1 — a foil copy of a printing that also exists in nonfoil.  The foil
    # prices are the right ones; the nonfoil ones are here to be picked wrongly.
    _add_card(conn, 1, "Alpha")
    _price(conn, 1, "tcgplayer", "foil", 12.5)
    _price(conn, 1, "cardkingdom", "buylist_foil", 9.0)
    _price(conn, 1, "tcgplayer", "normal", 1.0)
    _price(conn, 1, "cardkingdom", "buylist_normal", 0.5)
    _mtgjson(conn, 1, "https://ck/alpha", "https://ck/alpha-foil")

    # 2 — a double-faced card: two mtgjson rows share the printing_id, each
    # with its own Card Kingdom link.  The uuids are ordered against insertion
    # order so a join that sorted by uuid would pick the back face.
    _add_card(conn, 2, "Bravo")
    _price(conn, 2, "tcgplayer", "normal", 3.0)
    _mtgjson(conn, 2, "https://ck/bravo-front", "https://ck/bravo-front-foil", uuid_suffix="-z")
    _mtgjson(conn, 2, "https://ck/bravo-back", "https://ck/bravo-back-foil", uuid_suffix="-a")

    # 3 — a foil-only printing: there is no nonfoil price to fall back to.
    _add_card(conn, 3, "Charlie", finishes='["foil"]')
    _price(conn, 3, "tcgplayer", "foil", 40.0)
    _mtgjson(conn, 3, "", "https://ck/charlie-foil")

    # 4 — no prices and no mtgjson row at all.
    _add_card(conn, 4, "Delta")

    constructed = _deck(conn, "Constructed", 3)
    for n, finish in ((1, "foil"), (2, "nonfoil"), (3, "foil"), (4, "nonfoil")):
        cid = _own(conn, n, finish)
        conn.execute(
            "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone) "
            "VALUES (?, ?, ?, 'mainboard')",
            (constructed, f"print-{n}", cid),
        )

    idea = _deck(conn, "Idea", 1)
    for n in (1, 2, 3, 4):
        conn.execute(
            "INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity) "
            "VALUES (?, ?, 'mainboard', 1)",
            (idea, f"print-{n}"),
        )

    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path, constructed, idea
    os.unlink(path)


class _RecordingConn:
    """sqlite3.Connection proxy that records the parameter count of each execute."""

    def __init__(self, conn):
        self._conn = conn
        self.param_counts = []

    def execute(self, sql, params=()):
        self.param_counts.append(len(params))
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _make_handler(db_path, recording=False):
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()  # truthy, never called by this path
    handler._responses = []
    handler._conns = []
    handler._send_json = lambda obj, status=200: handler._responses.append((status, obj))

    if recording:
        real_get_conn = handler._get_conn

        def recording_get_conn():
            wrapped = _RecordingConn(real_get_conn())
            handler._conns.append(wrapped)
            return wrapped

        handler._get_conn = recording_get_conn

    return handler


def _deck_cards(db_path, deck_id, **params):
    handler = _make_handler(db_path)
    handler._api_deck_cards(deck_id, {k: [v] for k, v in params.items()})
    status, body = handler._responses[-1]
    assert status == 200, body
    return {c["name"]: c for c in body}


# ── A constructed deck holds copies, and prices each in its own finish ──


def test_foil_copy_uses_foil_prices(deck_db):
    """The deck page used to price a foil copy off the printing's finishes and
    show the nonfoil price for a card the collection page priced as foil."""
    path, constructed, _ = deck_db
    cards = _deck_cards(path, constructed)
    assert cards["Alpha"]["tcg_price"] == "12.5"
    assert cards["Alpha"]["ck_price"] == "9.0"


def test_deck_price_agrees_with_the_collection_list(deck_db):
    """Same copy, two pages, one number."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    path, constructed, _ = deck_db
    handler = object.__new__(CrackPackHandler)
    handler.db_path = path
    handler.generator = object()
    responses = []
    handler._send_json = lambda obj, status=200: responses.append(obj)
    handler._api_collection({})
    collection = {c["name"]: c for c in responses[-1]["rows"]}

    deck = _deck_cards(path, constructed)
    for name in ("Alpha", "Bravo", "Charlie", "Delta"):
        assert deck[name]["tcg_price"] == collection[name]["tcg_price"], name
        assert deck[name]["ck_price"] == collection[name]["ck_price"], name
        assert deck[name]["ck_url"] == collection[name]["ck_url"], name


def test_missing_prices_are_none_and_missing_url_is_empty(deck_db):
    path, constructed, _ = deck_db
    cards = _deck_cards(path, constructed)
    assert cards["Delta"]["tcg_price"] is None
    assert cards["Delta"]["ck_price"] is None
    assert cards["Delta"]["ck_url"] == ""


def test_ck_url_follows_the_copy_finish(deck_db):
    path, constructed, _ = deck_db
    cards = _deck_cards(path, constructed)
    assert cards["Alpha"]["ck_url"] == "https://ck/alpha-foil"
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front"


def test_duplicate_mtgjson_printing_id_agrees_with_get_ck_url(deck_db):
    """printing_id is not unique in mtgjson_printings — MTGJSON emits a row per
    face of a double-faced card, each with its own Card Kingdom link.  This
    endpoint kept whichever row came last, so a deck could link the same card
    to a different product than the collection list and the card detail page.
    """
    from mtg_collector.services.pack_generator import PackGenerator

    path, constructed, _ = deck_db
    cards = _deck_cards(path, constructed)
    gen = PackGenerator(path)
    assert cards["Bravo"]["ck_url"] == gen.get_ck_url("print-2", foil=False)
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front"


def test_enrichment_joins_do_not_multiply_rows(deck_db):
    """One row per deck entry, despite four enrichment joins and a card with
    two mtgjson rows."""
    path, constructed, _ = deck_db
    handler = _make_handler(path)
    handler._api_deck_cards(constructed, {})
    _, body = handler._responses[-1]
    assert len(body) == 4, [c["name"] for c in body]


def test_zone_filter_still_applies(deck_db):
    path, constructed, _ = deck_db
    handler = _make_handler(path)
    handler._api_deck_cards(constructed, {"zone": ["sideboard"]})
    _, body = handler._responses[-1]
    assert body == []


# ── An idea deck expects printings, and prices the printing ──


def test_expected_cards_price_on_the_printing(deck_db):
    """No copy is held, so a printing that exists in nonfoil prices in nonfoil
    and a foil-only one prices in foil."""
    path, _, idea = deck_db
    cards = _deck_cards(path, idea)
    assert cards["Bravo"]["tcg_price"] == "3.0"
    assert cards["Charlie"]["tcg_price"] == "40.0"


def test_expected_card_url_follows_the_printing(deck_db):
    path, _, idea = deck_db
    cards = _deck_cards(path, idea)
    assert cards["Alpha"]["ck_url"] == "https://ck/alpha"
    assert cards["Charlie"]["ck_url"] == "https://ck/charlie-foil"


# ── The assertion that keeps it fixed ──


def test_no_statement_binds_params_proportional_to_the_deck(deck_db):
    """Growing the deck must not grow any statement's parameter count.

    The enrichment used to build one `IN (...)` per unique printing and another
    per card in the deck.  A future "bulk lookup" that reintroduces the shape
    fails here.
    """
    path, constructed, _ = deck_db

    def _max_params():
        handler = _make_handler(path, recording=True)
        handler._api_deck_cards(constructed, {})
        status, body = handler._responses[-1]
        assert status == 200, body
        return max(c for conn in handler._conns for c in conn.param_counts), len(body)

    small_max, small_rows = _max_params()

    conn = sqlite3.connect(path)
    for n in range(100, 160):
        _add_card(conn, n, f"Extra {n:03d}")
        cid = _own(conn, n, "nonfoil")
        conn.execute(
            "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone) "
            "VALUES (?, ?, ?, 'mainboard')",
            (constructed, f"print-{n}", cid),
        )
    conn.commit()
    conn.close()

    large_max, large_rows = _max_params()

    assert large_rows > small_rows * 10
    assert large_max == small_max
