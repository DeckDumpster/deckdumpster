"""
Test _api_jumpstart_insert_deck handles duplicate lands and connection cleanup.

Two bugs combined to permanently lock the database:
1. Card list containing a land that also gets auto-appended (e.g. "Forest"
   in a green deck) creates a duplicate (printing_id, zone), violating
   the UNIQUE constraint on deck_expected_cards.
2. The resulting IntegrityError propagated without closing the connection,
   leaving a write transaction open and locking the DB for all threads.

To run: uv run pytest tests/test_jumpstart_insert_deck.py -v
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from mtg_collector.db.models import (
    Card,
    CardRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import init_db


@pytest.fixture
def db_path():
    """Create a temp database with schema and test cards for Jumpstart."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    set_repo = SetRepository(conn)
    card_repo = CardRepository(conn)
    printing_repo = PrintingRepository(conn)

    set_repo.upsert(Set(
        set_code="test", set_name="Test Set",
        set_type="expansion", digital=0))
    for oid, name, pid, cn in [
        ("o-bolt", "Lightning Bolt", "p-bolt", "1"),
        ("o-growth", "Giant Growth", "p-growth", "2"),
        ("o-thriving", "Thriving Grove", "p-thriving", "3"),
        ("o-forest", "Forest", "p-forest", "4"),
    ]:
        card_repo.upsert(Card(oracle_id=oid, name=name))
        printing_repo.upsert(Printing(
            printing_id=pid, oracle_id=oid,
            set_code="test", collector_number=cn))
    conn.commit()
    conn.close()

    yield path
    os.unlink(path)


def _make_handler(db_path):
    """Build a minimal mock CrackPackHandler with just enough to call the method."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler._responses = []

    def fake_send_json(obj, status=200):
        handler._responses.append((status, obj))

    handler._send_json = fake_send_json
    return handler


def test_successful_insert(db_path):
    """Basic smoke test: a valid insert creates a deck."""
    handler = _make_handler(db_path)
    handler._api_jumpstart_insert_deck({
        "color": "G",
        "theme": "Stompy",
        "cards": ["Lightning Bolt", "Giant Growth"],
    })
    assert handler._responses[-1][0] == 201
    resp = handler._responses[-1][1]
    assert resp["name"] == "Stompy (Jumpstart)"
    assert resp["deck_id"] > 0


def test_card_list_with_duplicate_land_succeeds(db_path):
    """Card list containing a land that also gets auto-appended must not crash.

    This is the exact production trigger: a green deck with "Forest" in the
    card list gets "Forest" appended again as the basic land. Without dedup,
    this creates a duplicate (printing_id, zone) and violates the UNIQUE
    constraint on deck_expected_cards.
    """
    handler = _make_handler(db_path)
    handler._api_jumpstart_insert_deck({
        "color": "G",
        "theme": "Landfall",
        "cards": ["Lightning Bolt", "Forest"],
    })
    assert handler._responses[-1][0] == 201
    resp = handler._responses[-1][1]
    # Forest should appear once with combined quantity
    forests = [c for c in resp["cards"] if c["name"] == "Forest"]
    assert len(forests) == 1
    assert forests[0]["quantity"] == 8  # 1 from card list + 7 default basics


def test_card_list_with_duplicate_thriving_land_succeeds(db_path):
    """Card list containing the thriving land must not crash."""
    handler = _make_handler(db_path)
    handler._api_jumpstart_insert_deck({
        "color": "G",
        "theme": "Ramp",
        "cards": ["Lightning Bolt", "Thriving Grove"],
    })
    assert handler._responses[-1][0] == 201
    resp = handler._responses[-1][1]
    groves = [c for c in resp["cards"] if c["name"] == "Thriving Grove"]
    assert len(groves) == 1
    assert groves[0]["quantity"] == 2  # 1 from card list + 1 auto-appended


def test_duplicate_deck_name_returns_409_without_locking(db_path):
    """Inserting a deck with a duplicate name returns 409 and doesn't lock the DB."""
    handler = _make_handler(db_path)

    handler._api_jumpstart_insert_deck({
        "color": "G",
        "theme": "Stompy",
        "cards": ["Lightning Bolt", "Giant Growth"],
    })
    assert handler._responses[-1][0] == 201

    # Second insert with same theme → 409 (duplicate deck name)
    handler._api_jumpstart_insert_deck({
        "color": "G",
        "theme": "Stompy",
        "cards": ["Lightning Bolt", "Giant Growth"],
    })
    assert handler._responses[-1][0] == 409

    # DB must still be writable
    conn = sqlite3.connect(db_path, timeout=2)
    conn.execute("INSERT INTO settings (key, value) VALUES ('test_key', 'ok')")
    conn.commit()
    conn.close()


def test_integrity_error_does_not_lock_db(db_path):
    """A UNIQUE constraint error mid-insert must not leave the DB locked.

    Simulates the production failure: an IntegrityError during
    INSERT INTO deck_expected_cards leaves conn open with an uncommitted
    write transaction, locking the DB for all subsequent writers.
    """
    # Pre-seed a deck_expected_cards row that will collide
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO decks (name, format, hypothetical, is_precon, created_at, updated_at)
           VALUES ('Collider (Jumpstart)', 'jumpstart', 1, 0, '2025-01-01', '2025-01-01')""")
    collider_deck_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity)
           VALUES (?, 'p-bolt', 'mainboard', 1)""",
        (collider_deck_id,))
    conn.commit()
    conn.close()

    handler = _make_handler(db_path)

    # Wrap sqlite3.Connection in a proxy that redirects last_insert_rowid()
    # to return the collider deck id, triggering a UNIQUE constraint violation.
    # Can't patch execute on the C-level Connection directly, so we use a proxy.
    real_connect = sqlite3.connect

    class ConnectionProxy:
        def __init__(self, real_conn, fake_deck_id):
            self._conn = real_conn
            self._fake_deck_id = fake_deck_id
            self.closed = False

        def execute(self, sql, params=()):
            if sql == "SELECT last_insert_rowid()":
                return self._conn.execute(
                    "SELECT ?", (self._fake_deck_id,))
            return self._conn.execute(sql, params)

        def commit(self):
            return self._conn.commit()

        def close(self):
            self.closed = True
            return self._conn.close()

        @property
        def row_factory(self):
            return self._conn.row_factory

        @row_factory.setter
        def row_factory(self, val):
            self._conn.row_factory = val

    proxy = None

    def rigged_connect(*args, **kwargs):
        nonlocal proxy
        conn = real_connect(*args, **kwargs)
        proxy = ConnectionProxy(conn, collider_deck_id)
        return proxy

    with patch("sqlite3.connect", side_effect=rigged_connect):
        # This will hit IntegrityError on deck_expected_cards insert.
        # Before the fix, the exception propagated without closing conn,
        # leaving a write lock. After the fix, finally closes it.
        try:
            handler._api_jumpstart_insert_deck({
                "color": "G",
                "theme": "Doomed",
                "cards": ["Lightning Bolt"],
            })
        except sqlite3.IntegrityError:
            pass

    # Verify the connection was closed by the finally block
    assert proxy is not None, "rigged_connect was never called"
    assert proxy.closed, "Connection was not closed — write lock would persist"

    # The critical assertion: DB must still be writable after the failed insert.
    # Before the fix, this would raise "database is locked".
    conn = sqlite3.connect(db_path, timeout=2)
    conn.execute("INSERT INTO settings (key, value) VALUES ('after_error', 'ok')")
    conn.commit()
    conn.close()
