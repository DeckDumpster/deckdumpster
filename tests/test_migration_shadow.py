"""In-place upgrade of a split-DB instance (de-w0v2).

A deployed instance serves its reference data from an ATTACHed `shared.sqlite`
through temp views that shadow every SHARED_TABLES name.  SQLite resolves an
unqualified name temp first, so DDL naming one of those tables finds the *view*:

    CREATE INDEX ... ON printings(...)   ->  views may not be indexed
    ALTER TABLE printings ADD COLUMN ..  ->  Cannot add a column to a view
    DROP VIEW IF EXISTS latest_sealed_prices -> silently drops the shadow

`deploy.sh` rebuilds the image and keeps the data volume, so an instance that
already exists is upgraded in place: init_db takes the migration branch with the
shadow up, and the first `mtg` command after the deploy crashes.  A freshly split
instance is already current and never reaches it.
"""

import sqlite3

import pytest

from mtg_collector.db.connection import (
    attach_shared,
    shadow_view_names,
)
from mtg_collector.db.schema import (
    _SHADOW_TRANSPARENT_MIGRATIONS,
    SCHEMA_VERSION,
    SHARED_TABLES,
    SHARED_VIEWS,
    _migrations,
    get_current_version,
    init_db,
)

# `mtg db split` shipped at SCHEMA_VERSION 41, so no database below that can
# have been split and none can carry a shadow.  41 is where the in-place upgrade
# path becomes reachable.
FIRST_SPLIT_ERA_VERSION = 41


def _seed(conn):
    """A set, a card, a printing and one owned copy of it."""
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")
    conn.execute(
        "INSERT INTO cards (oracle_id, name, type_line) "
        "VALUES ('oracle-1', 'Shadowed Card', 'Creature')"
    )
    conn.execute(
        "INSERT INTO printings "
        "(printing_id, oracle_id, set_code, collector_number, rarity, card_name) "
        "VALUES ('print-1', 'oracle-1', 'tst', '1', 'R', 'Shadowed Card')"
    )
    conn.execute(
        "INSERT INTO collection "
        "(printing_id, card_name, finish, status, source, acquired_at) "
        "VALUES ('print-1', 'Shadowed Card', 'nonfoil', 'owned', 'test', "
        "'2026-01-01T00:00:00.000Z')"
    )
    conn.commit()


def _split(main_path, shared_path):
    """Copy the reference tables to a shared DB and prune them from main.

    The shape `mtg db split --prune` leaves behind: main keeps every table
    definition and none of the reference rows.
    """
    shared = sqlite3.connect(shared_path)
    init_db(shared)
    shared.close()

    conn = sqlite3.connect(main_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ATTACH DATABASE ? AS shared", (shared_path,))
    for table in SHARED_TABLES:
        conn.execute(f"DELETE FROM shared.[{table}]")
        conn.execute(f"INSERT INTO shared.[{table}] SELECT * FROM main.[{table}]")
    for view in SHARED_VIEWS:
        exists = conn.execute(
            "SELECT 1 FROM shared.sqlite_master WHERE type='table' AND name=?", (view,)
        ).fetchone()
        if exists:
            conn.execute(f"DELETE FROM shared.[{view}]")
            conn.execute(f"INSERT INTO shared.[{view}] SELECT * FROM main.[{view}]")
    for name in list(SHARED_TABLES) + list(SHARED_VIEWS):
        exists = conn.execute(
            "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        if exists:
            conn.execute(f"DELETE FROM main.[{name}]")
    conn.commit()
    conn.execute("DETACH DATABASE shared")
    conn.close()


def _record_version(conn, version):
    """Roll the recorded version back; get_current_version reads MAX(version)."""
    conn.execute("DELETE FROM schema_version WHERE version > ?", (version,))
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, applied_at) "
        "VALUES (?, '2026-01-01T00:00:00Z')",
        (version,),
    )
    conn.commit()


@pytest.fixture
def split_instance(tmp_path):
    """A pruned split instance: (main path, shared path), both at the current version."""
    main_path = str(tmp_path / "collection.sqlite")
    shared_path = str(tmp_path / "shared.sqlite")

    conn = sqlite3.connect(main_path)
    init_db(conn)
    _seed(conn)
    conn.close()

    _split(main_path, shared_path)
    return main_path, shared_path


def _open_shadowed(main_path, shared_path):
    conn = sqlite3.connect(main_path)
    conn.row_factory = sqlite3.Row
    attach_shared(conn, shared_path)
    return conn


def _main_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA main.table_info({table})")}


def _main_indexes(conn):
    return {
        row[0]
        for row in conn.execute("SELECT name FROM main.sqlite_master WHERE type='index'")
    }


def test_v48_index_and_column_land_on_an_upgraded_split_instance(split_instance):
    """The bug this file exists for: v48's CREATE INDEX hit the shadow view.

    Undo v48's artifacts on main and roll the version back, so the migration has
    real work to do — an already-present index would hide nothing, since
    CREATE INDEX IF NOT EXISTS resolves the table before it checks the index.
    """
    main_path, shared_path = split_instance

    conn = sqlite3.connect(main_path)
    conn.execute("DROP INDEX IF EXISTS idx_printings_set_sortable")
    conn.execute("ALTER TABLE printings DROP COLUMN number_sortable")
    _record_version(conn, 47)
    conn.close()

    conn = _open_shadowed(main_path, shared_path)
    init_db(conn)

    # `shared.printings` was never rolled back, so with the shadow up
    # PRAGMA table_info reports the column as already present.  Only the main
    # table's own definition proves the ALTER reached the table.
    assert "number_sortable" in _main_columns(conn, "printings")
    assert "idx_printings_set_sortable" in _main_indexes(conn)
    conn.close()


def test_v45_recreates_the_main_view_not_the_shadow(split_instance):
    """v45 drops and recreates latest_sealed_prices, which the shadow also names.

    Unqualified DROP VIEW resolves temp first, so without the guard it removes
    the shadow — the connection then reads the emptied main tables for the rest
    of its life — and the CREATE VIEW that follows fails on the main-schema view
    it never dropped.
    """
    main_path, shared_path = split_instance

    conn = sqlite3.connect(main_path)
    _record_version(conn, 44)
    conn.close()

    conn = _open_shadowed(main_path, shared_path)
    init_db(conn)

    installed = {
        row[0] for row in conn.execute("SELECT name FROM temp.sqlite_master")
    }
    assert set(shadow_view_names()) <= installed
    # The shadow still routes at `shared`, where the seeded rows live.
    assert conn.execute("SELECT COUNT(*) FROM printings").fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("from_version", range(FIRST_SPLIT_ERA_VERSION, SCHEMA_VERSION))
def test_every_split_era_migration_survives_the_shadow(split_instance, from_version):
    """Replay the upgrade from each version a split instance can have been left at.

    No artifacts are removed, so the migrations are mostly no-ops on their own
    columns — but every CREATE INDEX and DROP VIEW still executes unconditionally,
    and those are what resolve to the shadow.

    This is a coverage floor, not a proof: `shared` here is current, so a
    migration that decides on `PRAGMA table_info` reads the view and sees its
    column already present.  The two targeted cases above do the proving.
    """
    main_path, shared_path = split_instance

    conn = sqlite3.connect(main_path)
    _record_version(conn, from_version)
    conn.close()

    conn = _open_shadowed(main_path, shared_path)
    init_db(conn)

    assert get_current_version(conn) == SCHEMA_VERSION
    installed = {
        row[0] for row in conn.execute("SELECT name FROM temp.sqlite_master")
    }
    assert set(shadow_view_names()) <= installed
    conn.close()


def test_the_v50_backfill_reads_the_shared_catalogue(split_instance):
    """The one migration that needs the shadow UP still gets it.

    v50 fills `collection.card_name` from `printings`.  On a pruned instance the
    names are only in `shared`, so suspending the shadow here would not fail —
    it would read the emptied `main.printings`, write NULL over every row, and
    take the owned sort's key with it.

    The column is left in place and stale rather than dropped: that is the
    upstream-rename case the backfill also repairs, and it makes the read the
    only thing under test.
    """
    main_path, shared_path = split_instance

    conn = sqlite3.connect(main_path)
    conn.execute("UPDATE collection SET card_name = 'Stale Name'")
    _record_version(conn, 49)
    conn.commit()
    conn.close()

    conn = _open_shadowed(main_path, shared_path)
    init_db(conn)

    assert "card_name" in _main_columns(conn, "collection")
    names = [
        row[0] for row in conn.execute("SELECT card_name FROM main.collection")
    ]
    assert names == ["Shadowed Card"]
    conn.close()


def test_the_migration_chain_is_discovered_and_complete():
    """The dispatch is the module, not a list written down beside it.

    A hand-written chain is a second copy of the same fact, and a missing line
    in it is a migration that exists and is never called.
    """
    chain = _migrations()
    assert [version for version, _ in chain] == list(range(2, SCHEMA_VERSION + 1))
    for version, migrate in chain:
        assert migrate.__name__ == f"_migrate_v{version - 1}_to_v{version}"


def test_every_shadow_transparent_name_is_a_real_migration():
    """A typo in the exemption list would silently guard a migration that must not be.

    The name is matched against `migrate.__name__`, so a misspelling does not
    raise — it just drops out of the frozenset lookup and the migration runs
    suspended, which for v50 means NULL over the sort key rather than an error.
    """
    names = {migrate.__name__ for _, migrate in _migrations()}
    assert _SHADOW_TRANSPARENT_MIGRATIONS <= names
