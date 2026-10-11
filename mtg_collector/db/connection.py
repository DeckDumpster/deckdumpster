"""Database connection management."""

import os
import sqlite3
from urllib.parse import quote
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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

    shared = get_shared_db_path()
    _connection = open_connection(path, shared)
    _db_path = path
    _attached = bool(shared) and os.path.abspath(path) != os.path.abspath(shared)

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


class SchemaTooNewError(Exception):
    """A database file records a schema newer than this code understands."""


class IsolationError(Exception):
    """A connection's attached databases are not the ones it was meant to have."""


def _ro_uri(path: str) -> str:
    return "file:" + quote(os.path.abspath(path)) + "?mode=ro"


def file_schema_version(conn, schema: str = "main") -> int:
    """Highest schema_version recorded in one attached file (0 if none)."""
    try:
        row = conn.execute(f"SELECT MAX(version) FROM [{schema}].schema_version").fetchone()
    except sqlite3.OperationalError:
        return 0
    return row[0] or 0


def refuse_if_newer(conn, schema: str = "main") -> None:
    """Raise if this file was written by newer code than this process runs."""
    from mtg_collector.db.schema import SCHEMA_VERSION

    found = file_schema_version(conn, schema)
    if found > SCHEMA_VERSION:
        raise SchemaTooNewError(
            f"{schema} database records schema version {found}, but this code "
            f"understands up to {SCHEMA_VERSION}. Deploy a newer build; "
            "refusing to open it."
        )


def attach_shared(conn, shared_db_path):
    """ATTACH the shared catalogue read-only and create temp views to shadow local tables.

    The connection must have been opened with uri=True (open_connection does).
    """
    conn.execute("ATTACH DATABASE ? AS shared", (_ro_uri(shared_db_path),))
    refuse_if_newer(conn, "shared")
    create_shared_shadow(conn)


def assert_isolated(conn, main_path: str, shared_path: Optional[str] = None) -> None:
    """Fail unless PRAGMA database_list is exactly {main: main_path[, shared: shared_path]}."""
    got = {
        row[1]: os.path.realpath(row[2])
        for row in conn.execute("PRAGMA database_list")
        if row[1] != "temp"
    }
    want = {"main": os.path.realpath(main_path)}
    if shared_path:
        want["shared"] = os.path.realpath(shared_path)
    if got != want:
        raise IsolationError(f"connection databases {got} != expected {want}")


def open_connection(
    path: str,
    shared_path: Optional[str] = None,
    *,
    timeout: float = 10.0,
    wal: bool = True,
) -> sqlite3.Connection:
    """The one place a connection is opened.

    Opens `path`, attaches `shared_path` (when it exists and is a different
    file) read-only, refuses either file if its recorded schema is newer than
    this code, and asserts the connection sees exactly those two files.
    """
    conn = sqlite3.connect("file:" + quote(os.path.abspath(path)), timeout=timeout, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        if wal:
            conn.execute("PRAGMA journal_mode = WAL")
        refuse_if_newer(conn, "main")
        split = bool(shared_path) and os.path.exists(shared_path) and (
            os.path.abspath(shared_path) != os.path.abspath(path)
        )
        if split:
            attach_shared(conn, shared_path)
            # FK enforcement is incompatible with ATTACH'd shared tables —
            # SQLite FK checks only see empty main-schema tables.
        else:
            conn.execute("PRAGMA foreign_keys = ON")
        assert_isolated(conn, path, shared_path if split else None)
    except BaseException:
        conn.close()
        raise
    return conn


def open_catalog_connection(db_path: str) -> sqlite3.Connection:
    """A read-only connection to the card catalogue and nothing else.

    In split mode that is the shared file alone, so a catalogue reader never
    holds a tenant file; in single-DB mode the catalogue lives in `db_path`.
    """
    shared = get_shared_db_path()
    target = shared if shared else db_path
    conn = sqlite3.connect(_ro_uri(target), timeout=10.0, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        refuse_if_newer(conn, "main")
        assert_isolated(conn, target)
    except BaseException:
        conn.close()
        raise
    return conn


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
