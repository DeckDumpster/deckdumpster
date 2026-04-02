"""Database connection management."""

import os
import sqlite3
from pathlib import Path
from typing import Optional

from mtg_collector.utils import get_mtgc_home

# Global connection cache
_connection: Optional[sqlite3.Connection] = None
_db_path: Optional[str] = None


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


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Get or create a database connection.

    Uses a cached connection for the same path.
    """
    global _connection, _db_path

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
    _connection = sqlite3.connect(path)
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA foreign_keys = ON")
    _db_path = path

    return _connection


def attach_shared(conn, shared_db_path):
    """ATTACH a shared reference DB and create temp views to shadow local tables.

    Also re-creates cross-schema views (collection_view, sealed_collection_view)
    as temp views so they resolve table references through the temp view chain
    instead of reading from empty main-schema tables.
    """
    from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS

    conn.execute("ATTACH DATABASE ? AS shared", (shared_db_path,))
    for table in SHARED_TABLES:
        conn.execute(f"CREATE TEMP VIEW IF NOT EXISTS [{table}] AS SELECT * FROM shared.[{table}]")
    for view in SHARED_VIEWS:
        conn.execute(f"CREATE TEMP VIEW IF NOT EXISTS [{view}] AS SELECT * FROM shared.[{view}]")

    # Re-create cross-schema views as temp views. Stored views in main resolve
    # table names in the main schema (empty user tables). Temp views resolve via
    # SQLite's temp → main → attached priority, hitting our temp view redirects.
    for view_name in ("collection_view", "sealed_collection_view"):
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


def close_connection():
    """Close the cached connection if one exists."""
    global _connection, _db_path

    if _connection is not None:
        _connection.close()
        _connection = None
        _db_path = None
