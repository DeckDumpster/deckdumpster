"""The joins /api/collection's count and totals bodies are built without.

`total`, `total_qty` and `total_value` come from bodies whose SELECT list reads
almost nothing, so most of the page's joins are walked for columns those bodies
never look at.  They are now emitted only when some fragment of the same body —
its SELECT list, its WHERE, or its conditional-join block — actually names the
alias (de-5l08).

Two things have to hold, and each has its own test below:

  * the joins really are dropped (otherwise the whole change is a no-op that
    still passes every value assertion), and
  * every figure the endpoint sends is unchanged by dropping them, on a
    database that exercises each relationship the dropped joins reach — orders,
    a deck holding one copy in two zones, a binder, a wishlist entry, and
    prices in both finishes.

`cards` and `sets` are dropped on an argument about data rather than about SQL:
a printing whose oracle_id or set_code has no parent row would be counted and
never paged.  The last test here is that guarantee — SQLite itself refuses the
orphan — rather than a comment claiming it.

To run: uv run pytest tests/test_collection_aggregate_joins.py -v
"""

import os
import re
import sqlite3
import tempfile

import pytest

from mtg_collector.db.schema import init_db, refresh_latest_prices

NOW = "2025-01-01T00:00:00.000Z"


# ── A database with something behind every dropped join ──


@pytest.fixture
def joined_db():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    conn.execute("INSERT INTO sets (set_code, set_name, released_at) VALUES ('tst', 'Test Set', '2020-01-01')")
    conn.execute(
        "INSERT INTO orders (id, order_number, source, seller_name, order_date, created_at) "
        "VALUES (1, 'ORD-1', 'tcgplayer', 'A Seller', '2024-12-01', ?)",
        (NOW,),
    )
    conn.execute(
        "INSERT INTO binders (id, name, created_at, updated_at) VALUES (1, 'Reds', ?, ?)",
        (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO decks (id, name, format, state_id, created_at, updated_at) "
        "VALUES (1, 'Burn', 'modern', 3, ?, ?)",
        (NOW, NOW),
    )

    # Nine cards, six of them owned: enough that a limit of 2 pages more than
    # once on every template here, so the short-page shortcut — which answers
    # the totals off the rows already in hand — never hides the statements
    # these tests are about.
    for n in range(1, 10):
        conn.execute(
            "INSERT INTO cards (oracle_id, name, type_line, mana_cost, cmc, colors, color_identity) "
            "VALUES (?, ?, ?, '{R}', 1, '[\"R\"]', '[\"R\"]')",
            (f"o{n}", f"Card {n}", "Creature — Goblin" if n <= 3 else "Instant"),
        )
        conn.execute(
            "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, "
            "finishes, card_name) VALUES (?, ?, 'tst', ?, 'rare', '[\"nonfoil\", \"foil\"]', ?)",
            (f"p{n}", f"o{n}", str(n), f"Card {n}"),
        )
        for source, price_type, price in [
            ("tcgplayer", "normal", 1.5 * n),
            ("tcgplayer", "foil", 100.0 * n),
            ("cardkingdom", "buylist_normal", 0.5 * n),
        ]:
            conn.execute(
                "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
                "VALUES ('tst', ?, ?, ?, ?, '2025-01-01')",
                (str(n), source, price_type, price),
            )

    # One nonfoil copy of each, plus a second copy of Card 1 in foil, so a
    # group's qty and a per-finish price both have more than one value to be
    # got wrong.
    def own(n, finish, **kw):
        cols = "printing_id, finish, acquired_at, source, status, card_name"
        vals = [f"p{n}", finish, NOW, "manual", "owned", f"Card {n}"]
        for k, v in kw.items():
            cols += f", {k}"
            vals.append(v)
        conn.execute(
            f"INSERT INTO collection ({cols}) VALUES ({','.join('?' * len(vals))})", vals
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Cards 7-9 stay unowned, so `is:unowned` has a result to page.
    first = own(1, "nonfoil", order_id=1)
    own(1, "foil")
    own(2, "nonfoil", binder_id=1)
    for n in range(3, 7):
        own(n, "nonfoil")

    # One copy in two deck zones: the fan-out `deck_cards` can produce, and the
    # reason `expand=copies` keeps that join while the grouped templates drop it.
    for zone in ("mainboard", "sideboard"):
        conn.execute(
            "INSERT INTO deck_cards (deck_id, collection_id, printing_id, zone) "
            "VALUES (1, ?, 'p3', ?)",
            (first + 5, zone),
        )
    conn.execute(
        "INSERT INTO wishlist (oracle_id, priority, added_at) VALUES ('o4', 1, ?)", (NOW,)
    )

    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


# ── Calling the endpoint ──


class _RecordingConn:
    """sqlite3.Connection proxy that keeps the text of every statement."""

    def __init__(self, conn):
        self._conn = conn
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _call(db_path, **params):
    """Run /api/collection and return (body, statements)."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))

    real_get_conn = handler._get_conn
    recorded = []

    def get_conn():
        wrapped = _RecordingConn(real_get_conn())
        recorded.append(wrapped)
        return wrapped

    handler._get_conn = get_conn
    handler._api_collection({k: [str(v)] for k, v in params.items()})
    status, body = responses[-1]
    assert status == 200, body
    return body, recorded[0].statements


def _aggregate_statements(statements):
    """The count and totals statements, which are the ones this change edits."""
    return [s for s in statements if s.lstrip().startswith("SELECT COUNT(*),")
            or s.lstrip().startswith("SELECT COALESCE(SUM(qty)")
            or s.lstrip().startswith("SELECT COUNT(*) FROM (SELECT 1 ")]


def _joined_tables(sql):
    return set(re.findall(r"(?:LEFT )?JOIN (\w+) ", sql))


# ── The joins are actually dropped ──


@pytest.mark.parametrize("params,absent", [
    ({}, {"cards", "sets", "orders", "deck_cards", "decks", "binders"}),
    ({"q": "is:unowned"}, {"cards", "sets", "orders"}),
    ({"q": "r:rare"}, {"cards", "sets", "orders", "deck_cards", "decks", "binders"}),
])
def test_an_aggregate_body_omits_the_joins_it_reads_nothing_from(joined_db, params, absent):
    _, statements = _call(joined_db, limit=2, **params)
    aggregates = _aggregate_statements(statements)
    assert aggregates, "no count or totals statement ran"
    for sql in aggregates:
        assert _joined_tables(sql) & absent == set(), sql


@pytest.mark.parametrize("query,table", [
    ("t:goblin", "cards"),          # card.type_line
    ("year:2020", "sets"),          # s.released_at
    ("is:wanted", "cards"),         # the wishlist join reads card.oracle_id
    ("deck:Burn", "decks"),         # d.name
    ("is:decked", "deck_cards"),    # dc.deck_id
    ("binder:Reds", "binders"),     # b.name
])
def test_a_join_the_where_or_another_join_reads_is_kept(joined_db, query, table):
    _, statements = _call(joined_db, limit=1, q=query)
    aggregates = _aggregate_statements(statements)
    assert aggregates, "no count or totals statement ran"
    for sql in aggregates:
        assert table in _joined_tables(sql), sql


def test_expand_copies_keeps_the_deck_cards_join(joined_db):
    """It pages one row per deck_cards row, so its aggregates must count them."""
    _, statements = _call(joined_db, expand="copies", limit=2)
    for sql in _aggregate_statements(statements):
        assert "deck_cards" in _joined_tables(sql), sql


# ── Every figure is unchanged ──


QUERIES = [
    {},
    {"q": "is:unowned"},
    {"q": "t:goblin"},
    {"q": "year:2020"},
    {"q": "is:decked"},
    {"q": "is:unassigned"},
    {"q": "binder:Reds"},
    {"q": "deck:Burn"},
    {"q": "is:wanted"},
    {"q": "r:rare"},
    {"expand": "copies"},
    {"expand": "copies", "q": "is:decked"},
    {"cards": "tst:1,tst:2"},
]


@pytest.mark.parametrize("params", QUERIES, ids=lambda p: str(p) or "default")
def test_total_matches_the_rows_the_page_actually_hands_back(joined_db, params):
    """The count is the one figure a wrongly dropped join would inflate."""
    body, _ = _call(joined_db, limit=2, **params)
    paged, offset = 0, 0
    while True:
        window, _ = _call(joined_db, limit=2, offset=offset, **params)
        paged += len(window["rows"])
        offset += len(window["rows"])
        if not window["rows"]:
            break
    assert body["total"] == paged


@pytest.mark.parametrize("params", QUERIES, ids=lambda p: str(p) or "default")
def test_the_totals_are_what_the_first_window_rows_add_up_to(joined_db, params):
    """total_qty and total_value describe the result, so page it and sum it.

    `tcg_price` is the column here because `price_sources` is unset and defaults
    to "tcg,ck" -- the totals are summed from whichever price the page shows.
    """
    body, _ = _call(joined_db, limit=2, **params)
    qty, value = 0, 0.0
    offset = 0
    while True:
        window, _ = _call(joined_db, limit=2, offset=offset, **params)
        if not window["rows"]:
            break
        offset += len(window["rows"])
        for row in window["rows"]:
            qty += row["qty"] or 0
            value += float(row["tcg_price"] or 0) * (row["qty"] or 0)
    assert body["total_qty"] == qty
    assert body["total_value"] == pytest.approx(round(value, 2))


# ── Why `cards` and `sets` may be dropped at all ──


def test_a_printing_cannot_be_written_without_its_card_and_set(joined_db):
    """The invariant the dropped INNER joins rest on, enforced by SQLite.

    Both aggregate bodies now count a printing without checking that its
    oracle_id and set_code resolve, so an orphan would be counted and never
    paged.  `printings` has exactly one INSERT site in this codebase, and every
    path that reaches it opens the catalogue through get_connection(), which is
    where foreign key enforcement is turned on.
    """
    from mtg_collector.db.connection import close_connection, get_connection

    close_connection()
    conn = get_connection(joined_db)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number) "
                "VALUES ('orphan-card', 'no-such-oracle', 'tst', '900')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number) "
                "VALUES ('orphan-set', 'o1', 'nope', '901')"
            )
    finally:
        close_connection()


def test_the_shipped_catalogue_holds_no_orphan_printings():
    """The other half, against a catalogue the ingest paths really built.

    tests/fixtures/test-data.sqlite is 7,645 printings pulled through
    `mtg cache` and `mtg data import` by scripts/build_test_fixture.py, so it is
    the closest thing in the repo to evidence about what those paths produce.
    Regenerating it after an ingest change is what would catch a new writer that
    leaves a printing behind without its card or its set.
    """
    fixture = os.path.join(
        os.path.dirname(__file__), "fixtures", "test-data.sqlite"
    )
    conn = sqlite3.connect(f"file:{fixture}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM printings").fetchone()[0] > 0
        assert conn.execute(
            "SELECT COUNT(*) FROM printings p LEFT JOIN cards c ON p.oracle_id = c.oracle_id "
            "WHERE c.oracle_id IS NULL"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM printings p LEFT JOIN sets s ON p.set_code = s.set_code "
            "WHERE s.set_code IS NULL"
        ).fetchone()[0] == 0
    finally:
        conn.close()
