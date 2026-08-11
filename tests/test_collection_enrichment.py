"""
Price and Card Kingdom URL enrichment on /api/collection.

The enrichment used to be two follow-up passes after the main query, each
building an `IN (...)` clause sized by the result set.  It is now LEFT JOINs on
the main query.  These tests pin the enrichment values that refactor had to
preserve, and — more durably — assert that no statement in the path binds a
number of parameters that grows with the result set.

To run: uv run pytest tests/test_collection_enrichment.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.schema import init_db, refresh_latest_prices

NOW = "2025-01-01T00:00:00.000Z"


def _add_card(conn, n, name, set_code="tst"):
    """Insert card + printing #n and return its printing_id."""
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors, color_identity) "
        "VALUES (?, ?, '{R}', 'Creature', '[\"R\"]', '[\"R\"]')",
        (f"oracle-{n}", name),
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes) "
        "VALUES (?, ?, ?, ?, 'R', '[\"nonfoil\", \"foil\"]')",
        (f"print-{n}", f"oracle-{n}", set_code, str(n)),
    )
    return f"print-{n}"


def _own(conn, n, finish):
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


def _mtgjson(conn, n, ck_url, ck_url_foil, uuid_suffix=""):
    conn.execute(
        "INSERT INTO mtgjson_printings (uuid, printing_id, name, set_code, number, ck_url, ck_url_foil, imported_at) "
        "VALUES (?, ?, 'x', 'tst', ?, ?, ?, '2025-01-01')",
        (f"uuid-{n}{uuid_suffix}", f"print-{n}", str(n), ck_url, ck_url_foil),
    )


@pytest.fixture
def enriched_db():
    """A DB exercising every branch of the price / ck_url enrichment."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")

    # 1 — nonfoil, both a CK buylist and a CK retail price: buylist wins.
    _add_card(conn, 1, "Alpha")
    _own(conn, 1, "nonfoil")
    _price(conn, 1, "tcgplayer", "normal", 5.99)
    _price(conn, 1, "cardkingdom", "buylist_normal", 3.0)
    _price(conn, 1, "cardkingdom", "normal", 4.0)
    _price(conn, 1, "tcgplayer", "foil", 99.0)  # must NOT be picked for a nonfoil copy
    _mtgjson(conn, 1, "https://ck/alpha", "https://ck/alpha-foil")

    # 2 — foil, no CK buylist: falls back to the CK retail foil price.  Two
    # mtgjson rows share the printing_id, as MTGJSON emits for a double-faced
    # card.  The uuids are ordered against insertion order on purpose, so a
    # join that sorted by uuid would pick the back face and fail the test.
    _add_card(conn, 2, "Bravo")
    _own(conn, 2, "foil")
    _price(conn, 2, "tcgplayer", "foil", 12.5)
    _price(conn, 2, "cardkingdom", "foil", 9.0)
    _price(conn, 2, "tcgplayer", "normal", 1.0)  # must NOT be picked for a foil copy
    _mtgjson(conn, 2, "https://ck/bravo-front", "https://ck/bravo-front-foil", uuid_suffix="-z")
    _mtgjson(conn, 2, "https://ck/bravo-back", "https://ck/bravo-back-foil", uuid_suffix="-a")

    # 3 — etched prices as foil, and falls back to the nonfoil URL when there
    # is no foil one.
    _add_card(conn, 3, "Charlie")
    _own(conn, 3, "etched")
    _price(conn, 3, "tcgplayer", "foil", 20.0)
    _price(conn, 3, "cardkingdom", "buylist_foil", 15.0)
    _price(conn, 3, "tcgplayer", "normal", 2.0)  # must NOT be picked for an etched copy
    _mtgjson(conn, 3, "https://ck/charlie", "")

    # 4 — no prices and no mtgjson row at all.
    _add_card(conn, 4, "Delta")
    _own(conn, 4, "nonfoil")

    # 5 — not owned: c.finish is NULL, so it prices as normal.
    _add_card(conn, 5, "Echo")
    _price(conn, 5, "tcgplayer", "normal", 7.25)
    _price(conn, 5, "tcgplayer", "foil", 70.0)
    _mtgjson(conn, 5, "https://ck/echo", "https://ck/echo-foil")

    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
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
    """Build a minimal mock CrackPackHandler that captures _send_json output."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()  # truthy, never called by this path
    handler._responses = []
    handler._conns = []

    def fake_send_json(obj, status=200):
        handler._responses.append((status, obj))

    handler._send_json = fake_send_json

    if recording:
        real_get_conn = handler._get_conn

        def recording_get_conn():
            wrapped = _RecordingConn(real_get_conn())
            handler._conns.append(wrapped)
            return wrapped

        handler._get_conn = recording_get_conn

    return handler


def _collection(db_path, **params):
    handler = _make_handler(db_path)
    handler._api_collection({k: [v] for k, v in params.items()})
    status, body = handler._responses[-1]
    assert status == 200, body
    return {c["name"]: c for c in body}


# ── Enrichment values ──


def test_buylist_price_wins_over_retail(enriched_db):
    """CK buylist is preferred; TCG price follows the copy's finish."""
    cards = _collection(enriched_db)
    assert cards["Alpha"]["ck_price"] == "3.0"
    assert cards["Alpha"]["tcg_price"] == "5.99"


def test_foil_copy_falls_back_to_retail_and_uses_foil_prices(enriched_db):
    """No buylist_foil row, so the CK retail foil price is used — never normal."""
    cards = _collection(enriched_db)
    assert cards["Bravo"]["ck_price"] == "9.0"
    assert cards["Bravo"]["tcg_price"] == "12.5"


def test_etched_prices_as_foil(enriched_db):
    """Etched copies price as foil, not normal."""
    cards = _collection(enriched_db)
    assert cards["Charlie"]["ck_price"] == "15.0"
    assert cards["Charlie"]["tcg_price"] == "20.0"


def test_missing_prices_are_none(enriched_db):
    cards = _collection(enriched_db)
    assert cards["Delta"]["ck_price"] is None
    assert cards["Delta"]["tcg_price"] is None


def test_ck_url_follows_finish(enriched_db):
    """Nonfoil gets ck_url, foil gets ck_url_foil."""
    cards = _collection(enriched_db)
    assert cards["Alpha"]["ck_url"] == "https://ck/alpha"
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front-foil"


def test_ck_url_foil_falls_back_to_nonfoil(enriched_db):
    """An etched copy with an empty ck_url_foil uses the nonfoil URL."""
    cards = _collection(enriched_db)
    assert cards["Charlie"]["ck_url"] == "https://ck/charlie"


def test_ck_url_missing_is_empty_string(enriched_db):
    cards = _collection(enriched_db)
    assert cards["Delta"]["ck_url"] == ""


def test_duplicate_mtgjson_printing_id_agrees_with_get_ck_url(enriched_db):
    """printing_id is not unique in mtgjson_printings — MTGJSON emits a row per
    face of a double-faced card, each with its own Card Kingdom link.

    The list must resolve the same row the card detail page does, or the two
    pages link the same card to different products.
    """
    from mtg_collector.services.pack_generator import PackGenerator

    cards = _collection(enriched_db)
    gen = PackGenerator(enriched_db)
    assert cards["Bravo"]["ck_url"] == gen.get_ck_url("print-2", foil=True)
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front-foil"


def test_enrichment_survives_the_shared_reference_db(enriched_db, tmp_path):
    """Deployed instances read cards/prices/mtgjson through ATTACHed shadow views.

    Those views have no rowid, so an enrichment join that leans on one resolves
    to NULL and silently drops every price and URL.
    """
    from mtg_collector.db.schema import SHARED_TABLES

    shared = str(tmp_path / "shared.sqlite")
    user = str(tmp_path / "user.sqlite")
    __import__("shutil").copy(enriched_db, shared)
    conn = sqlite3.connect(shared)
    conn.execute("DELETE FROM collection")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(user)
    init_db(conn)
    conn.close()
    conn = sqlite3.connect(user)
    conn.execute("ATTACH DATABASE ? AS full", (enriched_db,))
    conn.execute("INSERT INTO collection SELECT * FROM full.collection")
    for table in SHARED_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

    from mtg_collector.cli import crack_pack_server

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(crack_pack_server, "_shared_db_path", shared)
        cards = _collection(user)

    assert cards["Alpha"]["ck_price"] == "3.0"
    assert cards["Alpha"]["tcg_price"] == "5.99"
    assert cards["Alpha"]["ck_url"] == "https://ck/alpha"
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front-foil"


def test_enrichment_applies_to_unowned_template(enriched_db):
    """The is:unowned LEFT JOIN template enriches too, pricing a NULL finish as normal."""
    cards = _collection(enriched_db, q="is:unowned")
    assert cards["Echo"]["tcg_price"] == "7.25"
    assert cards["Echo"]["ck_url"] == "https://ck/echo"


def test_enrichment_applies_to_expand_copies_template(enriched_db):
    """The one-row-per-copy template enriches too, without duplicating rows."""
    handler = _make_handler(enriched_db)
    handler._api_collection({"expand": ["copies"]})
    _, body = handler._responses[-1]
    assert len(body) == 4, [c["name"] for c in body]
    cards = {c["name"]: c for c in body}
    assert cards["Bravo"]["ck_price"] == "9.0"
    assert cards["Bravo"]["ck_url"] == "https://ck/bravo-front-foil"


def test_enrichment_joins_do_not_multiply_rows(enriched_db):
    """One row per owned card, despite four enrichment joins."""
    handler = _make_handler(enriched_db)
    handler._api_collection({})
    _, body = handler._responses[-1]
    assert len(body) == 4, [c["name"] for c in body]


# ── The assertion that keeps it fixed ──


def _max_params(db_path, **params):
    handler = _make_handler(db_path, recording=True)
    handler._api_collection({k: [v] for k, v in params.items()})
    status, body = handler._responses[-1]
    assert status == 200, body
    return max(c for conn in handler._conns for c in conn.param_counts), len(body)


def test_no_statement_binds_params_proportional_to_the_result_set(enriched_db):
    """Growing the result set must not grow any statement's parameter count.

    The enrichment used to build `IN (...)` clauses from the result set: at
    112,809 rows that was 225,618 bound parameters against a
    SQLITE_MAX_VARIABLE_NUMBER of 250,000.  A future "bulk lookup" that
    reintroduces the shape fails here.
    """
    small_max, small_rows = _max_params(enriched_db)

    conn = sqlite3.connect(enriched_db)
    for n in range(100, 160):
        _add_card(conn, n, f"Extra {n:03d}")
        _own(conn, n, "nonfoil")
    conn.commit()
    conn.close()

    large_max, large_rows = _max_params(enriched_db)

    assert large_rows > small_rows * 10
    assert large_max == small_max
