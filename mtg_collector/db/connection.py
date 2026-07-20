"""Database connection management."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from mtg_collector.utils import get_mtgc_home

# Global connection cache
_connection: Optional[sqlite3.Connection] = None
_db_path: Optional[str] = None
_attached: bool = False


def get_db_path(override: Optional[str] = None) -> str:
    """
    Get the database path.

    Priority:
    1. Explicit override parameter
    2. MTGC_DB environment variable
    3. Default: $HOME/.mtgc/collection.sqlite
    """
    if override:
        return override

    env_path = os.environ.get("MTGC_DB")
    if env_path:
        return env_path

    default_dir = get_mtgc_home()
    return str(default_dir / "collection.sqlite")


def get_shared_db_path() -> Optional[str]:
    """Return MTGC_SHARED_DB path if set and exists, else None."""
    path = os.environ.get("MTGC_SHARED_DB")
    if path and os.path.exists(path):
        return path
    return None


def get_shared_write_path(default_path: str) -> str:
    """Return the DB path where shared table data should be written.

    In split mode (MTGC_SHARED_DB set), returns the shared DB path so
    that cache/import commands write reference data to the shared file.
    In single-DB mode, returns the default path unchanged.
    """
    shared = get_shared_db_path()
    return shared if shared else default_path


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Get or create a database connection.

    Uses a cached connection for the same path.
    Automatically ATTACHes a shared reference DB if MTGC_SHARED_DB is set.
    """
    global _connection, _db_path, _attached

    path = get_db_path(db_path)

    # Return cached connection if path matches
    if _connection is not None and _db_path == path:
        return _connection

    # Close existing connection if path changed
    if _connection is not None:
        _connection.close()

    # Ensure directory exists
    db_dir = Path(path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Create new connection
    _connection = sqlite3.connect(path, timeout=10.0)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA journal_mode = WAL")
    # FK enforcement is deferred until after potential ATTACH — see below
    _db_path = path
    _attached = False

    # Auto-ATTACH shared reference DB if configured
    # Skip if this connection IS the shared DB (write-path for import commands)
    shared = get_shared_db_path()
    if shared and os.path.abspath(path) != os.path.abspath(shared):
        attach_shared(_connection, shared)
        _attached = True
    else:
        # Only enable FK enforcement when NOT using split DB.
        # With ATTACH, temp views shadow the main tables but SQLite FK checks
        # only look at main-schema tables (which are empty after prune),
        # causing false constraint failures.
        _connection.execute("PRAGMA foreign_keys = ON")

    return _connection


#: Cross-schema views re-created as temp views so they resolve through the
#: shadow chain instead of reading from the emptied main-schema tables.
_CROSS_SCHEMA_VIEWS = ("collection_view", "sealed_collection_view")


def shadow_view_names():
    """Every temp view name create_shared_shadow() installs."""
    from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS

    return list(SHARED_TABLES) + list(SHARED_VIEWS) + list(_CROSS_SCHEMA_VIEWS)


def shared_is_attached(conn) -> bool:
    """True when a `shared` database is ATTACHed to this connection."""
    return any(row[1] == "shared" for row in conn.execute("PRAGMA database_list"))


def attach_shared(conn, shared_db_path):
    """ATTACH a shared reference DB and create temp views to shadow local tables."""
    conn.execute("ATTACH DATABASE ? AS shared", (shared_db_path,))
    create_shared_shadow(conn)


def create_shared_shadow(conn):
    """Create the temp views that route reads at the ATTACHed `shared` DB.

    Requires `shared` to already be ATTACHed.  Split out from attach_shared() so
    the shadow can be rebuilt without re-ATTACHing — see suspend_shared_shadow().
    """
    from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS

    for table in SHARED_TABLES:
        conn.execute(f"CREATE TEMP VIEW IF NOT EXISTS [{table}] AS SELECT * FROM shared.[{table}]")
    for view in SHARED_VIEWS:
        conn.execute(f"CREATE TEMP VIEW IF NOT EXISTS [{view}] AS SELECT * FROM shared.[{view}]")

    # Stored views in main resolve table names in the main schema (empty user
    # tables). Temp views resolve via SQLite's temp → main → attached priority,
    # hitting our temp view redirects.
    for view_name in _CROSS_SCHEMA_VIEWS:
        row = conn.execute(
            "SELECT sql FROM main.sqlite_master WHERE type='view' AND name=?",
            (view_name,),
        ).fetchone()
        if not row:
            continue
        sql = row[0]
        conn.execute(f"DROP VIEW IF EXISTS temp.[{view_name}]")
        # Rewrite "CREATE VIEW collection_view" → "CREATE TEMP VIEW collection_view"
        temp_sql = sql.replace(f"CREATE VIEW IF NOT EXISTS {view_name}", f"CREATE TEMP VIEW {view_name}", 1)
        temp_sql = temp_sql.replace(f"CREATE VIEW {view_name}", f"CREATE TEMP VIEW {view_name}", 1)
        conn.execute(temp_sql)


def drop_shared_shadow(conn):
    """Drop the temp views create_shared_shadow() installed."""
    for name in shadow_view_names():
        conn.execute(f"DROP VIEW IF EXISTS temp.[{name}]")


@contextmanager
def suspend_shared_shadow(conn):
    """Run a block with the temp shadow views removed, then restore them.

    The shadow is a *read* routing mechanism: it makes `SELECT ... FROM cards`
    reach `shared.cards` on a connection whose `main.cards` was emptied by
    `db split --prune`.  It has no business being visible to DDL.  While it is
    installed, SQLite resolves unqualified names temp → main → attached, so
    `CREATE INDEX ... ON latest_prices` finds the temp *view* shadowing the
    main-schema table and fails with "views may not be indexed".

    DETACHing `shared` is not sufficient: the temp views outlive the DETACH and
    keep shadowing the same names.  The shadow itself has to come down.

    A no-op when no shared DB is attached, so single-DB deployments are
    unaffected.
    """
    if not shared_is_attached(conn):
        yield
        return

    drop_shared_shadow(conn)
    try:
        yield
    finally:
        create_shared_shadow(conn)


def close_connection():
    """Close the cached connection if one exists."""
    global _connection, _db_path, _attached

    if _connection is not None:
        _connection.close()
        _connection = None
        _db_path = None
        _attached = False
