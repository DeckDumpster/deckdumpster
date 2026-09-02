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
        # card_name is the denormalised sort key PrintingRepository.upsert fills;
        # written here too, because collection.card_name is copied from it.
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, card_name) "
        "VALUES ('print-1', 'oracle-1', 'tst', '1', 'R', 'Split Test Card')"
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


def test_a_collection_write_fills_card_name_through_the_shadow(monolithic_db):
    """collection.card_name is filled by the INSERT, and must be under split-DB too.

    This is why it is a scalar subquery in the statement and not a trigger: after
    a prune `main.printings` is empty and the real catalogue is behind a temp
    view over the ATTACHed shared DB. An ordinary statement resolves through
    that shadow; a trigger body in `main` cannot see temp views at all, so it
    would write NULL here — silently, and only on the deployments that use this
    mode. NULL is unrecoverable at read time: it is what the default collection
    page sorts on.
    """
    from mtg_collector.cli.db_cmd import run_split
    from mtg_collector.db.models import CollectionEntry, CollectionRepository

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = True

    run_split(FakeArgs())

    conn = sqlite3.connect(monolithic_db)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_path)
    # Nothing to read the name from in this database itself.
    assert conn.execute("SELECT COUNT(*) FROM main.printings").fetchone()[0] == 0

    new_id = CollectionRepository(conn).add(
        CollectionEntry(
            id=None,
            printing_id="print-1",
            finish="foil",
            acquired_at="2025-02-02T00:00:00.000Z",
            source="manual",
            status="owned",
        )
    )
    conn.commit()
    name = conn.execute(
        "SELECT card_name FROM collection WHERE id = ?", (new_id,)
    ).fetchone()[0]
    conn.close()
    os.unlink(shared_path)
    assert name == "Split Test Card"


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


# ── Column pairing: `db split` must not depend on column ORDER ──


def _synthetic_row(conn, table):
    """One row for `table` whose value in every column names that column.

    A misaligned copy is only visible if no two columns hold the same value,
    so the value *is* the column name. Integer primary keys are the exception:
    a rowid alias rejects text outright, and rejecting is not the failure this
    is looking for — they get a number past anything the fixture already used.
    """
    info = conn.execute(f"PRAGMA main.table_info([{table}])").fetchall()
    values = []
    for i, col in enumerate(info):
        rowid_alias = col["pk"] == 1 and (col["type"] or "").upper() == "INTEGER"
        values.append(1_000_001 + i if rowid_alias else f"{table}.{col['name']}")
    names = ", ".join(f"[{c['name']}]" for c in info)
    holes = ", ".join("?" * len(info))
    conn.execute(f"INSERT INTO main.[{table}] ({names}) VALUES ({holes})", values)


def _redeclare(conn, table, reorder):
    """Rebuild `main.<table>`, its columns declared in `reorder(columns)` order.

    This is what a migration history does in miniature: ALTER TABLE ADD COLUMN
    appends, so a database that arrived at the current version through
    migrations carries an order SCHEMA_SQL never declared. It is the source
    side that has it — the shared DB is always built fresh from SCHEMA_SQL.

    Constraints are deliberately dropped from the rebuilt table: they belong to
    the shared side, and leaving them here would let a NOT NULL catch a
    misalignment on the way out that the two nullable columns of de-w49v would
    have let through.
    """
    info = {c["name"]: c for c in conn.execute(f"PRAGMA main.table_info([{table}])")}
    names = ", ".join(f"[{n}]" for n in info)
    decls = ", ".join(f"[{n}] {info[n]['type']}" for n in reorder(list(info)))
    # Without this, RENAME tries to fix up every view that names the table and
    # errors on the ones it cannot resolve mid-rebuild.
    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.execute(f"ALTER TABLE main.[{table}] RENAME TO [{table}__ordered]")
    conn.execute(f"CREATE TABLE main.[{table}] ({decls})")
    conn.execute(
        f"INSERT INTO main.[{table}] ({names}) "
        f"SELECT {names} FROM main.[{table}__ordered]"
    )
    conn.execute(f"DROP TABLE main.[{table}__ordered]")
    conn.execute("PRAGMA legacy_alter_table = OFF")


def _rows_by_name(conn, schema, table, columns):
    names = ", ".join(f"[{c}]" for c in columns)
    return sorted(
        (tuple(r) for r in conn.execute(f"SELECT {names} FROM {schema}.[{table}]")),
        key=repr,
    )


def test_split_pairs_columns_by_name_not_position(monolithic_db):
    """Every shared table survives a source whose column order isn't SCHEMA_SQL's.

    `shared` is created fresh from SCHEMA_SQL; a real source reached the same
    version through migrations, and ALTER TABLE ADD COLUMN appends. The two
    orders agree only where SCHEMA_SQL happens to declare each migration-added
    column in that same trailing position — which nothing checks, and which
    de-xpu broke by declaring mtgjson_printings.side beside the column it
    belongs with. `SELECT *` pairs by position, so it wrote side into
    imported_at; NOT NULL is the only reason that was loud rather than shipped.
    """
    from mtg_collector.cli.db_cmd import run_split

    conn = sqlite3.connect(monolithic_db)
    conn.row_factory = sqlite3.Row
    # latest_prices is materialized, so it is copied the same way; the other
    # entry in SHARED_VIEWS is a real view and the split skips it.
    materialized = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM main.sqlite_master WHERE type = 'table'"
        )
    }
    tables = [t for t in SHARED_TABLES + SHARED_VIEWS if t in materialized]
    assert "latest_prices" in tables

    expected = {}
    for table in tables:
        _synthetic_row(conn, table)
        _redeclare(conn, table, lambda cols: cols[::-1])
        cols = [r[1] for r in conn.execute(f"PRAGMA main.table_info([{table}])")]
        expected[table] = (cols, _rows_by_name(conn, "main", table, cols))
    conn.commit()
    conn.close()

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False

    run_split(FakeArgs())

    shared = sqlite3.connect(shared_path)
    shared.row_factory = sqlite3.Row
    try:
        for table in tables:
            cols, rows = expected[table]
            assert _rows_by_name(shared, "main", table, cols) == rows, (
                f"{table} copied into the wrong columns"
            )
    finally:
        shared.close()
        os.unlink(shared_path)


def test_split_refuses_a_source_column_the_shared_schema_lacks(monolithic_db):
    """A column SCHEMA_SQL never declared is an error, not a silent shift.

    This is the state a migration that adds a column without adding it to
    SCHEMA_SQL leaves behind, and under `SELECT *` it is exactly the off-by-one
    that de-xpu hit.
    """
    from mtg_collector.cli.db_cmd import run_split

    conn = sqlite3.connect(monolithic_db)
    conn.execute("ALTER TABLE printings ADD COLUMN undeclared_by_schema_sql TEXT")
    conn.commit()
    conn.close()

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False

    with pytest.raises(ValueError, match="undeclared_by_schema_sql"):
        run_split(FakeArgs())

    os.unlink(shared_path)


def test_split_refuses_a_source_missing_a_shared_column(monolithic_db):
    """A source behind the shared schema is an error, not a column of defaults."""
    from mtg_collector.cli.db_cmd import run_split

    conn = sqlite3.connect(monolithic_db)
    conn.row_factory = sqlite3.Row
    info = conn.execute("PRAGMA main.table_info([sets])").fetchall()
    kept = [c["name"] for c in info if c["name"] != "base_set_size"]
    names = ", ".join(f"[{c}]" for c in kept)
    conn.execute("PRAGMA legacy_alter_table = ON")
    conn.execute("ALTER TABLE sets RENAME TO sets__full")
    conn.execute(f"CREATE TABLE sets ({', '.join(f'[{c}] TEXT' for c in kept)})")
    conn.execute(f"INSERT INTO sets ({names}) SELECT {names} FROM sets__full")
    conn.execute("DROP TABLE sets__full")
    conn.commit()
    conn.close()

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False

    with pytest.raises(ValueError, match="base_set_size"):
        run_split(FakeArgs())

    os.unlink(shared_path)


def test_split_of_two_swapped_nullable_columns_is_caught(monolithic_db):
    """The misalignment nothing else would notice.

    cards.type_line and cards.mana_cost are adjacent, both nullable, both TEXT.
    Transposed under `SELECT *` each lands in the other and every constraint is
    satisfied — the copy succeeds and the shared catalogue ships with the mana
    cost in the type line. de-xpu was only loud because the column it displaced
    was NOT NULL.
    """
    from mtg_collector.cli.db_cmd import run_split

    def swap(cols):
        i, j = cols.index("type_line"), cols.index("mana_cost")
        cols[i], cols[j] = cols[j], cols[i]
        return cols

    conn = sqlite3.connect(monolithic_db)
    conn.row_factory = sqlite3.Row
    _redeclare(conn, "cards", swap)
    conn.commit()
    conn.close()

    shared_path = monolithic_db.replace(".sqlite", "-shared.sqlite")

    class FakeArgs:
        db_path = monolithic_db
        shared_out = shared_path
        prune = False

    run_split(FakeArgs())

    shared = sqlite3.connect(shared_path)
    row = shared.execute(
        "SELECT type_line, mana_cost FROM cards WHERE oracle_id = 'oracle-1'"
    ).fetchone()
    shared.close()
    os.unlink(shared_path)
    assert row == ("Creature", "{W}")
