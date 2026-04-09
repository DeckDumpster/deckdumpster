"""Tests for `mtg db split` and get_connection() auto-ATTACH."""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from mtg_collector.db.connection import (
    attach_shared,
    get_connection,
    get_shared_write_path,
    close_connection,
)
from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, init_db


# ── Fixtures ──


@pytest.fixture
def monolithic_db():
    """Create a monolithic DB with both shared and user data."""
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
        "VALUES ('oracle-1', 'Split Test Card', '{W}', 'Creature', '[\"W\"]')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
        "VALUES ('print-1', 'oracle-1', 'tst', '1', 'R')"
    )
    conn.execute(
        "INSERT INTO collection (printing_id, status, finish, condition, acquired_at, source) "
        "VALUES ('print-1', 'owned', 'nonfoil', 'Near Mint', '2025-01-01', 'manual')"
    )
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('tst', '1', 'tcgplayer', 'normal', 2.50, '2025-01-01T00:00:00')"
    )
    from mtg_collector.db.schema import refresh_latest_prices
    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


@pytest.fixture(autouse=True)
def clean_connection_cache():
    """Ensure the global connection cache is clean between tests."""
    close_connection()
    yield
    close_connection()


# ── mtg db split tests ──


def test_split_copies_shared_tables(monolithic_db):
    """db split copies shared table data into the new shared DB."""
    from mtg_collector.cli.db_cmd import run_split

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False

    run_split(FakeArgs())

    # Shared DB has the data
    shared = sqlite3.connect(shared_path)
    assert shared.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert shared.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 1
    assert shared.execute("SELECT COUNT(*) FROM printings").fetchone()[0] == 1
    assert shared.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 1
    assert shared.execute("SELECT COUNT(*) FROM latest_prices").fetchone()[0] == 1
    shared.close()

    # Source still has everything (no prune)
    source = sqlite3.connect(monolithic_db)
    assert source.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert source.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1
    source.close()

    os.unlink(shared_path)


def test_split_with_prune(monolithic_db):
    """db split --prune removes shared data from source."""
    from mtg_collector.cli.db_cmd import run_split

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = True

    run_split(FakeArgs())

    # Shared DB has data
    shared = sqlite3.connect(shared_path)
    assert shared.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    shared.close()

    # Source has shared tables emptied, user tables kept
    source = sqlite3.connect(monolithic_db)
    assert source.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert source.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 0
    assert source.execute("SELECT COUNT(*) FROM printings").fetchone()[0] == 0
    assert source.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1
    source.close()

    os.unlink(shared_path)


def test_split_then_attach_round_trip(monolithic_db):
    """After split+prune, user DB + ATTACH shared DB works end to end."""
    from mtg_collector.cli.db_cmd import run_split

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = True

    run_split(FakeArgs())

    # Open user DB, ATTACH shared
    conn = sqlite3.connect(monolithic_db)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_path)

    # Can read shared data via temp views
    card = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
    assert card["name"] == "Split Test Card"

    # Can read user data
    assert conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1

    # collection_view joins across both DBs
    rows = conn.execute("SELECT name, status FROM collection_view").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "Split Test Card"
    assert rows[0]["status"] == "owned"

    conn.close()
    os.unlink(shared_path)


# ── get_connection() auto-ATTACH tests ──


def test_get_connection_auto_attaches(monolithic_db):
    """get_connection() auto-ATTACHes when MTGC_SHARED_DB is set."""
    from mtg_collector.cli.db_cmd import run_split

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = True

    run_split(FakeArgs())

    with patch.dict(os.environ, {"MTGC_SHARED_DB": shared_path}):
        conn = get_connection(monolithic_db)
        # Reads resolve to shared DB
        card = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
        assert card["name"] == "Split Test Card"
        # User data is accessible
        assert conn.execute("SELECT COUNT(*) FROM collection").fetchone()[0] == 1

    os.unlink(shared_path)


def test_get_connection_no_attach_without_env(monolithic_db):
    """get_connection() works normally when MTGC_SHARED_DB is not set."""
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("MTGC_SHARED_DB", None)
        conn = get_connection(monolithic_db)
        card = conn.execute("SELECT name FROM cards WHERE oracle_id = 'oracle-1'").fetchone()
        assert card["name"] == "Split Test Card"


def test_get_connection_skips_attach_for_shared_db(monolithic_db):
    """get_connection() doesn't ATTACH the shared DB to itself."""
    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    from mtg_collector.cli.db_cmd import run_split
    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False
    run_split(FakeArgs())

    with patch.dict(os.environ, {"MTGC_SHARED_DB": shared_path}):
        # Opening the shared DB directly should NOT try to ATTACH itself
        conn = get_connection(shared_path)
        # Should have data (it IS the shared DB)
        assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
        # Should NOT have a 'shared' schema attached
        schemas = [r[1] for r in conn.execute("PRAGMA database_list").fetchall()]
        assert "shared" not in schemas

    os.unlink(shared_path)


# ── get_shared_write_path tests ──


def test_get_shared_write_path_returns_shared_when_set(monolithic_db):
    with patch.dict(os.environ, {"MTGC_SHARED_DB": "/tmp/shared.sqlite"}):
        with patch("mtg_collector.db.connection.os.path.exists", return_value=True):
            assert get_shared_write_path("/default.sqlite") == "/tmp/shared.sqlite"


def test_get_shared_write_path_returns_default_when_unset():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("MTGC_SHARED_DB", None)
        assert get_shared_write_path("/default.sqlite") == "/default.sqlite"
