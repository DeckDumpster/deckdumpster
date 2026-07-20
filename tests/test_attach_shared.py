"""
Test ATTACH-based shared reference DB.

Exercises both the low-level attach_shared() function and the server's
_get_conn() path in default (single-DB) and shared-DB modes.

To run: uv run pytest tests/test_attach_shared.py -v
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from mtg_collector.db.connection import attach_shared
from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, init_db


# ── Fixtures ──


@pytest.fixture
def shared_db_path():
    """Create a shared reference DB with schema and test data."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    conn.execute(
        "INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')"
    )
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors) "
        "VALUES ('oracle-1', 'Shared Card', '{R}', 'Creature', '[\"R\"]')"
    )
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors) "
        "VALUES ('oracle-2', 'Another Shared Card', '{G}', 'Instant', '[\"G\"]')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
        "VALUES ('print-1', 'oracle-1', 'tst', '1', 'R')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
        "VALUES ('print-2', 'oracle-2', 'tst', '2', 'U')"
    )
    # Populate latest_prices (materialized table)
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('tst', '1', 'tcgplayer', 'normal', 5.99, '2025-01-01T00:00:00')"
    )
    from mtg_collector.db.schema import refresh_latest_prices
    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def user_db_path():
    """Create an empty user DB with schema."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture
def single_db_path():
    """Create a single DB with both reference and user data (default mode)."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    conn.execute(
        "INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')"
    )
    conn.execute(
        "INSERT INTO cards (oracle_id, name, mana_cost, type_line, colors) "
        "VALUES ('oracle-1', 'Local Card', '{R}', 'Creature', '[\"R\"]')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
        "VALUES ('print-1', 'oracle-1', 'tst', '1', 'R')"
    )
    conn.execute(
        "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
        "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01T00:00:00', 'manual')"
    )
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('tst', '1', 'tcgplayer', 'normal', 3.50, '2025-01-01T00:00:00')"
    )
    from mtg_collector.db.schema import refresh_latest_prices
    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


# ── Low-level attach_shared() tests ──


def test_attach_creates_temp_views(user_db_path, shared_db_path):
    conn = sqlite3.connect(user_db_path)
    attach_shared(conn, shared_db_path)

    temp_views = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_temp_master WHERE type='view'"
        ).fetchall()
    ]
    for table in SHARED_TABLES:
        assert table in temp_views, f"Missing temp view for {table}"
    for view in SHARED_VIEWS:
        assert view in temp_views, f"Missing temp view for {view}"
    conn.close()


def test_reads_resolve_to_shared_db(user_db_path, shared_db_path):
    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_db_path)

    row = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
    assert row is not None
    assert row["name"] == "Shared Card"

    # User DB's own cards table is empty
    assert conn.execute("SELECT COUNT(*) FROM main.cards").fetchone()[0] == 0
    conn.close()


def test_writes_go_to_user_db(user_db_path, shared_db_path):
    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_db_path)

    conn.execute(
        "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
        "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01T00:00:00', 'manual')"
    )
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM main.collection").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM shared.collection").fetchone()[0] == 0
    conn.close()


def test_without_attach_works_normally(single_db_path):
    """Without ATTACH, everything works as a single DB."""
    conn = sqlite3.connect(single_db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
    assert row["name"] == "Local Card"
    assert conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1
    conn.close()


# ── Server _get_conn() tests ──


def _make_handler(db_path):
    """Build a minimal mock CrackPackHandler."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler._responses = []

    def fake_send_json(obj, status=200):
        handler._responses.append((status, obj))

    handler._send_json = fake_send_json
    return handler


def test_get_conn_default_mode(single_db_path):
    """_get_conn() without MTGC_SHARED_DB returns a plain connection."""
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        conn = handler._get_conn()
        row = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
        assert row["name"] == "Local Card"
        assert conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1
        conn.close()


def test_get_conn_shared_mode(user_db_path, shared_db_path):
    """_get_conn() with MTGC_SHARED_DB ATTACHes and creates temp views."""
    handler = _make_handler(user_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", shared_db_path):
        conn = handler._get_conn()

        # Reads reference data from shared DB
        row = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
        assert row["name"] == "Shared Card"

        # User DB's cards table is empty (reads redirected via temp view)
        assert conn.execute("SELECT COUNT(*) FROM main.cards").fetchone()[0] == 0

        # Can write to user tables
        conn.execute(
            "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
            "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01T00:00:00', 'manual')"
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM main.collection").fetchone()[0] == 1
        conn.close()


def test_get_conn_shared_mode_nonexistent_path(single_db_path):
    """_get_conn() with MTGC_SHARED_DB pointing to a missing file falls back to default."""
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", "/nonexistent/shared.sqlite"):
        conn = handler._get_conn()
        row = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
        assert row["name"] == "Local Card"
        conn.close()


# ── Repository layer through ATTACH ──


def test_collection_view_with_attach(user_db_path, shared_db_path):
    """collection_view joins cards + printings + sets — all from shared DB."""
    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_db_path)

    # Add a collection entry via raw SQL (references shared printing)
    conn.execute(
        "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
        "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01T00:00:00', 'manual')"
    )
    conn.commit()

    # collection_view denormalizes across shared + user data
    rows = conn.execute("SELECT * FROM collection_view").fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["name"] == "Shared Card"
    assert row["set_code"] == "tst"
    assert row["status"] == "owned"
    conn.close()


def test_collection_view_default_mode(single_db_path):
    """collection_view works normally in single-DB mode."""
    conn = sqlite3.connect(single_db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT * FROM collection_view").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "Local Card"
    conn.close()


def test_deck_with_attach(user_db_path, shared_db_path):
    """Decks work through ATTACH — deck cards reference shared printings."""
    from mtg_collector.db.models import Deck, DeckRepository

    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_db_path)

    repo = DeckRepository(conn)
    deck_id = repo.add(Deck(id=None, name="Test Deck"))
    conn.commit()

    # Add collection entry and assign to deck
    conn.execute(
        "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
        "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01T00:00:00', 'manual')"
    )
    conn.commit()
    col_id = conn.execute("SELECT id FROM collection WHERE printing_id = 'print-1'").fetchone()[0]
    repo.add_cards(deck_id, [col_id])
    conn.commit()

    cards = repo.get_cards(deck_id)
    assert len(cards) == 1
    assert cards[0]["name"] == "Shared Card"
    conn.close()


def test_card_search_with_attach(user_db_path, shared_db_path):
    """Card name search works through ATTACH."""
    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_db_path)

    rows = conn.execute("SELECT * FROM cards WHERE name LIKE '%Shared%'").fetchall()
    assert len(rows) == 2

    row = conn.execute("SELECT * FROM cards WHERE name = 'Shared Card'").fetchone()
    assert row is not None
    assert row["oracle_id"] == "oracle-1"
    conn.close()


def test_multiple_connections_independent(user_db_path, shared_db_path):
    """Each connection gets its own ATTACH — no cross-contamination."""
    conn1 = sqlite3.connect(user_db_path)
    conn1.row_factory = sqlite3.Row
    attach_shared(conn1, shared_db_path)

    conn2 = sqlite3.connect(user_db_path)
    conn2.row_factory = sqlite3.Row
    # conn2 does NOT attach

    # conn1 sees shared data via temp views
    assert conn1.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 2
    # conn2 sees only local (empty) data
    assert conn2.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0

    conn1.close()
    conn2.close()


# ── Price lookup with ATTACH ──


def test_get_sqlite_price_with_shared(user_db_path, shared_db_path):
    """_get_sqlite_price reads from shared DB when _shared_db_path is set."""
    from mtg_collector.cli.crack_pack_server import _get_sqlite_price

    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", shared_db_path):
        price = _get_sqlite_price(user_db_path, "tst", "1", "tcgplayer", "normal")
        assert price == "5.99"


def test_get_sqlite_price_default_mode(single_db_path):
    """_get_sqlite_price reads from main DB when no shared DB is set."""
    from mtg_collector.cli.crack_pack_server import _get_sqlite_price

    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        price = _get_sqlite_price(single_db_path, "tst", "1", "tcgplayer", "normal")
        assert price == "3.5"


# ── busy_timeout prevents instant lock failures ──


def test_handler_write_error_does_not_lock_db(single_db_path):
    """Handler write methods must not lock the DB when an exception occurs.

    Reproduces the production bug: _api_put_settings opens a connection and
    writes, but if an error occurs before conn.close(), the connection leaks
    and holds the write lock permanently, blocking all other writers.

    The fix is wrapping writes in try/finally so conn.close() always runs.
    """
    handler = _make_handler(single_db_path)
    # Stub _read_json_body to return data with a poison value that crashes
    # during the str(value) call inside the write loop
    class Bomb:
        def __str__(self):
            raise RuntimeError("disk on fire")

    handler._read_json_body = lambda: {"good_key": "good_val", "bad_key": Bomb()}

    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        # Call the handler — it writes "good_key" then explodes on "bad_key"
        try:
            handler._api_put_settings()
        except RuntimeError:
            pass

        # The bug: without try/finally, the connection leaks with an open
        # write transaction, locking the DB for all subsequent writers.
        # With try/finally, conn.close() runs and the lock is released.
        conn2 = sqlite3.connect(single_db_path, timeout=1)
        conn2.execute("INSERT INTO settings (key, value) VALUES ('after_error', 'ok')")
        conn2.commit()
        conn2.close()

    check = sqlite3.connect(single_db_path)
    row = check.execute("SELECT value FROM settings WHERE key = 'after_error'").fetchone()
    assert row is not None
    assert row[0] == "ok"
    check.close()


# ── Connection-leak regression tests (efj-mtgc-656) ──
#
# Each of these handlers opened a connection with _get_conn() and closed it only
# on its success / early-return paths. Any other exception escaped before
# conn.close(), leaking the connection — the traceback keeps the handler frame
# (and therefore the connection) alive, so it is never GC'd.
#
# When the escaping error happens *after* the handler has already written, the
# leaked connection is still inside an open write transaction. Under WAL that
# pins the single write lock and every later write fails "database is locked"
# until the process restarts. Reads keep working, so the service looks healthy
# while silently refusing all mutations.
#
# Every test asserts, in order:
#   1. the original exception still propagates (pytest.raises)
#   2. handler._responses == []  — the fix must not swallow the error into a
#      tidy JSON body (CLAUDE.md: "NEVER add fallback logic")
#   3. every connection the handler opened is now closed
# and, for the handlers that write before failing, additionally that a
# subsequent independent write succeeds (the write lock was really released).


def _seed_deck_fixtures(db_path):
    """Add a deck and a one-card batch to the standard single-DB fixture."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO decks (id, name, state_id, created_at, updated_at) "
        "VALUES (1, 'Test Deck', 1, '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO batches (id, batch_uuid, name, batch_type, created_at) "
        "VALUES (1, 'batch-uuid-1', 'Test Batch', 'manual', '2025-01-01T00:00:00')"
    )
    conn.execute("UPDATE collection SET batch_id = 1")
    conn.commit()
    conn.close()


def _call_expecting_leak(handler, fn, exc_type):
    """Run fn() expecting exc_type; assert it propagated and nothing leaked.

    Spies on sqlite3.connect so we can prove every connection the handler
    opened was actually closed — that is the invariant try/finally restores,
    and it holds whether or not a write transaction was open at the time.
    """
    import mtg_collector.cli.crack_pack_server as cps

    created = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        created.append(conn)
        return conn

    with patch.object(cps.sqlite3, "connect", spy):
        with pytest.raises(exc_type):
            fn()

    # The error must reach the caller, not become a tidy JSON error response.
    assert handler._responses == []
    assert created, "handler opened no connection — test trigger is wrong"
    for conn in created:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def _assert_lock_released(db_path, key):
    """The WAL write lock must be free: an independent writer must succeed."""
    conn = sqlite3.connect(db_path, timeout=1)
    conn.execute("INSERT INTO settings (key, value) VALUES (?, 'ok')", (key,))
    conn.commit()
    conn.close()

    check = sqlite3.connect(db_path)
    row = check.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    assert row is not None
    assert row[0] == "ok"
    check.close()


# --- Handlers that write before failing: these wedge the DB when leaked. ---


def test_deck_expected_set_error_does_not_lock_db(single_db_path):
    """set_expected_cards() DELETEs, then hits UNIQUE(deck_id, printing_id, zone).

    The DELETE opens the write transaction, so the leaked connection holds the
    WAL write lock.
    """
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_deck_expected_set(1, {"cards": [
                {"printing_id": "print-1", "zone": "mainboard"},
                {"printing_id": "print-1", "zone": "mainboard"},
            ]}),
            sqlite3.IntegrityError,
        )
        _assert_lock_released(single_db_path, "after_expected_set_error")


def test_deck_materialize_error_does_not_lock_db(single_db_path):
    """An expected card whose zone deck_cards' CHECK rejects.

    deck_expected_cards.zone has no CHECK, but materialize_deck() copies it
    into deck_cards.zone, which does. CHECK constraints fire regardless of
    PRAGMA foreign_keys, so this also reproduces in the split-DB deployment.
    """
    _seed_deck_fixtures(single_db_path)
    conn = sqlite3.connect(single_db_path)
    conn.execute(
        "INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity) "
        "VALUES (1, 'print-1', 'bogus_zone', 1)"
    )
    conn.commit()
    conn.close()

    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler, lambda: handler._api_deck_materialize(1),
            sqlite3.IntegrityError,
        )
        _assert_lock_released(single_db_path, "after_materialize_error")


def test_batch_assign_deck_error_does_not_lock_db(single_db_path):
    """deck_cards' zone CHECK raises IntegrityError past the except ValueError.

    Same shape as the efj-mtgc-7rp reproduction: the handler caught only
    ValueError, so IntegrityError escaped before conn.close().
    """
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_batch_assign_deck(
                1, {"deck_id": 1, "deck_zone": "bogus_zone"}),
            sqlite3.IntegrityError,
        )
        _assert_lock_released(single_db_path, "after_batch_assign_error")


# --- Handlers that fail before their first write. No write transaction is
# --- open, so the WAL lock is not held; the leak is still a leaked connection
# --- and is asserted as such.


def test_deck_create_error_does_not_leak_conn(single_db_path):
    """int(origin_variation) raises after the connection is already open."""
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_deck_create(
                {"name": "X", "origin_variation": "abc"}),
            ValueError,
        )


def test_deck_update_error_does_not_leak_conn(single_db_path):
    """An unbindable parameter escapes DeckRepository.update()."""
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_deck_update(1, {"name": {"unbindable": 1}}),
            sqlite3.ProgrammingError,
        )


def test_deck_delete_error_does_not_leak_conn(single_db_path):
    """An unbindable deck_id escapes DeckRepository.delete()."""
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_deck_delete({"unbindable": 1}),
            sqlite3.ProgrammingError,
        )


def test_deck_reassemble_error_does_not_leak_conn(single_db_path):
    """An unbindable collection_id escapes DeckRepository.move_cards()."""
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_deck_reassemble(
                1, {"collection_ids": [{"unbindable": 1}]}),
            sqlite3.ProgrammingError,
        )


def test_builder_create_error_does_not_leak_conn(single_db_path):
    """An unbindable deck name escapes past the handler's except ValueError."""
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_builder_create({
                "commander_oracle_id": "oracle-1",
                "state": "constructed",
                "name": {"unbindable": 1},
            }),
            sqlite3.ProgrammingError,
        )


def test_builder_remove_card_error_does_not_leak_conn(single_db_path):
    """An unbindable collection_id escapes DeckRepository.remove_cards()."""
    _seed_deck_fixtures(single_db_path)
    handler = _make_handler(single_db_path)
    with patch("mtg_collector.cli.crack_pack_server._shared_db_path", None):
        _call_expecting_leak(
            handler,
            lambda: handler._api_builder_remove_card(
                1, {"collection_id": {"unbindable": 1}}),
            sqlite3.ProgrammingError,
        )
