"""
Schema integrity checks (efj-mtgc-wys).

A current version number is not proof the DDL ever ran.  If a version is
recorded without its migration executing, init_db's early return skips the
change permanently.  These tests pin the check that catches it.

To run: uv run pytest tests/test_schema_integrity.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.connection import attach_shared
from mtg_collector.db.schema import (
    SCHEMA_OBJECTS,
    SCHEMA_VERSION,
    SHARED_TABLES,
    SHARED_VIEWS,
    SchemaIntegrityError,
    init_db,
    verify_schema,
    verify_shared_schema,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


# ── The object registry ──


def test_registry_covers_the_documented_tables():
    """Objects named in the issue must be in the expected set."""
    for name in (
        "sealed_products",
        "sealed_collection",
        "sealed_prices",
        "tcgplayer_groups",
    ):
        assert name in SCHEMA_OBJECTS


def test_registry_holds_tables_views_and_indexes():
    assert "collection" in SCHEMA_OBJECTS  # table
    assert "collection_view" in SCHEMA_OBJECTS  # view
    assert "idx_collection_status" in SCHEMA_OBJECTS  # index
    assert "cards_fts" in SCHEMA_OBJECTS  # virtual table


def test_registry_covers_both_latest_price_objects():
    """latest_prices is a TABLE, latest_sealed_prices is a VIEW.

    The check keys on name, not type, so a release that flips one to the other
    does not need the registry updated.
    """
    assert "latest_prices" in SCHEMA_OBJECTS
    assert "latest_sealed_prices" in SCHEMA_OBJECTS


# ── verify_schema ──


def test_intact_db_reports_nothing_missing(db):
    assert verify_schema(db) == []


def test_dropped_table_is_reported(db):
    db.execute("DROP TABLE sealed_products")
    assert "sealed_products" in verify_schema(db)


def test_dropped_view_is_reported(db):
    db.execute("DROP VIEW latest_sealed_prices")
    assert "latest_sealed_prices" in verify_schema(db)


def test_dropped_index_is_reported(db):
    db.execute("DROP INDEX idx_collection_status")
    assert "idx_collection_status" in verify_schema(db)


def test_empty_tables_are_not_reported_as_missing(db):
    """Presence, never population — an empty DB is a valid DB."""
    assert db.execute("SELECT COUNT(*) FROM printings").fetchone()[0] == 0
    assert verify_schema(db) == []


# ── The bug: a current version is not proof the DDL ran ──


def test_init_db_rejects_current_version_with_missing_tables():
    """The exact prod failure: version says 'done', v17->v18 tables are absent.

    Before the fix init_db returns False here and the damage surfaces much
    later as 'no such table: sealed_products' inside `mtg data fetch`.
    """
    conn = sqlite3.connect(":memory:")
    init_db(conn)

    for table in ("sealed_prices", "sealed_collection", "sealed_products"):
        conn.execute(f"DROP TABLE {table}")
    conn.execute("DROP TABLE tcgplayer_groups")

    # The version is untouched and current — the only evidence init_db has.
    assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == (
        SCHEMA_VERSION
    )

    with pytest.raises(SchemaIntegrityError) as exc:
        init_db(conn)

    message = str(exc.value)
    for table in (
        "sealed_products",
        "sealed_collection",
        "sealed_prices",
        "tcgplayer_groups",
    ):
        assert table in message, f"{table} not named in the error"
    assert "mtg db init --force" in message

    conn.close()


def test_intact_db_still_short_circuits(db):
    """An intact DB is silent and still reports 'nothing to do'."""
    assert init_db(db) is False


def test_force_repairs_a_damaged_db():
    """The documented remedy actually works and keeps existing rows."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')"
    )
    conn.commit()
    conn.execute("DROP TABLE sealed_products")

    assert init_db(conn, force=True) is True
    assert verify_schema(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 1
    conn.close()


# ── Split DB: the false-alarm trap ──


@pytest.fixture
def split_dbs():
    """A user DB whose reference tables are pruned, plus a shared DB.

    Mirrors `mtg db split --prune`, which deploy/setup.sh runs: the rows move
    to shared.sqlite and main's copies are emptied but not dropped.
    """
    fds = []
    for _ in range(2):
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        fds.append(path)
    user_path, shared_path = fds

    shared = sqlite3.connect(shared_path)
    init_db(shared)
    shared.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test')")
    shared.commit()
    shared.close()

    user = sqlite3.connect(user_path)
    init_db(user)
    for table in SHARED_TABLES:
        user.execute(f"DELETE FROM {table}")
    for view in SHARED_VIEWS:
        # latest_prices is a table in main; latest_sealed_prices is a view.
        row = user.execute(
            "SELECT type FROM main.sqlite_master WHERE name=?", (view,)
        ).fetchone()
        if row and row[0] == "table":
            user.execute(f"DELETE FROM {view}")
    user.commit()
    user.close()

    yield user_path, shared_path

    for path in fds:
        os.unlink(path)


def test_split_db_is_not_a_false_alarm(split_dbs):
    """main.printings is empty BY DESIGN — that must not read as damage."""
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)

    assert conn.execute("SELECT COUNT(*) FROM main.printings").fetchone()[0] == 0
    assert verify_schema(conn) == []
    assert init_db(conn) is False
    conn.close()


def test_split_db_still_detects_real_damage(split_dbs):
    """A table missing from every schema is still caught under split-DB."""
    user_path, shared_path = split_dbs

    for path in (user_path, shared_path):
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE sealed_products")
        conn.commit()
        conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    # attach_shared leaves a temp view named sealed_products behind even though
    # its target is gone; the check must not be fooled by it.
    assert conn.execute(
        "SELECT 1 FROM temp.sqlite_master WHERE name='sealed_products'"
    ).fetchone()
    assert "sealed_products" in verify_schema(conn)
    with pytest.raises(SchemaIntegrityError, match="sealed_products"):
        init_db(conn)
    conn.close()


def test_object_present_only_in_shared_counts_as_present(split_dbs):
    """An object dropped from main but live in shared is not missing."""
    user_path, shared_path = split_dbs

    conn = sqlite3.connect(user_path)
    conn.execute("DROP TABLE tcgplayer_groups")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    assert "tcgplayer_groups" not in verify_schema(conn)
    conn.close()


# ── The remedy must work where the error is raised (efj-mtgc-9hs) ──
#
# The integrity check above tells the operator to run `mtg db init --force`.
# Under split-DB that command aborted with "views may not be indexed": the temp
# views attach_shared() installs shadow the main-schema tables, so the
# CREATE INDEX on latest_prices in SCHEMA_SQL hit a view.  A check that
# recommends a broken remedy is worse than no check.


def test_force_repair_succeeds_under_split_db(split_dbs):
    """`mtg db init --force` must run on the connection the server actually uses.

    Before the fix this raised
    sqlite3.OperationalError: views may not be indexed.
    """
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)

    # The shadow is up: latest_prices is a TABLE in main and a VIEW in temp.
    assert conn.execute(
        "SELECT type FROM main.sqlite_master WHERE name='latest_prices'"
    ).fetchone()[0] == "table"
    assert conn.execute(
        "SELECT type FROM temp.sqlite_master WHERE name='latest_prices'"
    ).fetchone()[0] == "view"

    assert init_db(conn, force=True) is True
    conn.close()


def test_force_repair_recreates_an_index_the_shadow_hides(split_dbs):
    """The repair is genuine: the index really lands in main, not skipped."""
    user_path, shared_path = split_dbs
    for path in (user_path, shared_path):
        conn = sqlite3.connect(path)
        conn.execute("DROP INDEX idx_latest_prices_card")
        conn.commit()
        conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    assert "idx_latest_prices_card" in verify_schema(conn)

    init_db(conn, force=True)

    assert conn.execute(
        "SELECT 1 FROM main.sqlite_master WHERE name='idx_latest_prices_card'"
    ).fetchone()
    assert verify_schema(conn) == []
    conn.close()


def test_shadow_is_restored_after_the_repair(split_dbs):
    """Suspending the shadow for DDL must not leave the connection degraded."""
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)

    init_db(conn, force=True)

    # The temp views are back...
    assert conn.execute(
        "SELECT type FROM temp.sqlite_master WHERE name='latest_prices'"
    ).fetchone()[0] == "view"
    # ...and unqualified reads still route to shared, not to the emptied main.
    assert conn.execute("SELECT COUNT(*) FROM main.sets").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == 1
    conn.close()


def test_damaged_split_db_reports_then_the_named_remedy_repairs_it(split_dbs):
    """End to end: detect, run exactly what the message says, come back clean."""
    user_path, shared_path = split_dbs
    for path in (user_path, shared_path):
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE sealed_products")
        conn.commit()
        conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)

    with pytest.raises(SchemaIntegrityError) as exc:
        init_db(conn)
    assert "mtg db init --force" in str(exc.value)

    # Run the remedy the message named, on this same split-DB connection.
    assert init_db(conn, force=True) is True
    assert verify_schema(conn) == []
    assert init_db(conn) is False
    conn.close()


# ── The shared DB needs its own pass ──


def test_shared_gap_is_invisible_to_the_boot_path_check(split_dbs):
    """An object live in main but missing from shared is masked by the union.

    This is why verify_shared_schema exists.  The union is still the right rule
    for init_db: `db split --prune` only empties main, so main legitimately
    keeps every definition in a healthy split deployment.
    """
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(shared_path)
    conn.execute("DROP TABLE sealed_products")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    assert verify_schema(conn) == []  # masked by main's surviving definition
    assert init_db(conn) is False  # so the server still boots
    conn.close()


def test_verify_shared_schema_reports_the_shared_gap(split_dbs):
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(shared_path)
    conn.execute("DROP TABLE sealed_products")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    assert "sealed_products" in verify_shared_schema(conn)
    conn.close()


def test_verify_shared_schema_is_quiet_on_an_intact_split_db(split_dbs):
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    assert verify_shared_schema(conn) == []
    conn.close()


def test_verify_shared_schema_is_empty_without_a_shared_db(db):
    """Single-DB deployments have no shared schema to check."""
    assert verify_shared_schema(db) == []


def test_force_does_not_claim_to_repair_the_shared_db(split_dbs):
    """--force repairs main only; the shared gap must survive it, not be hidden.

    Production mounts the shared volume read-only, so this is a real limit of
    the remedy, not something to paper over.
    """
    user_path, shared_path = split_dbs
    conn = sqlite3.connect(shared_path)
    conn.execute("DROP TABLE sealed_products")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(user_path)
    attach_shared(conn, shared_path)
    init_db(conn, force=True)
    assert "sealed_products" in verify_shared_schema(conn)
    conn.close()


def test_force_is_unaffected_without_a_shared_db(db):
    """Single-DB deployments keep the old behaviour — the suspend is a no-op."""
    db.execute("DROP TABLE sealed_products")
    assert init_db(db, force=True) is True
    assert verify_schema(db) == []
