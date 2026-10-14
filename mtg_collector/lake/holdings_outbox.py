"""Reading and re-driving the holdings outbox (lakehouse K4).

The triggers in `db/schema.py` (HOLDINGS_OUTBOX_SQL) append to `holdings_outbox`
in the mutation's own transaction.  This module is the other half: `emit`
re-appends every current row (backfill for rows that predate the triggers,
redrive after a lost shipment, DR after a restore) and `fold` reduces the log
to the holdings it describes.  Both are idempotent in effect, because a reader
keeps the highest `seq` per (source, row_id): emitting twice changes the log,
never the folded result.
"""

import re
import sqlite3

from mtg_collector.lake.resolve import resolve

SOURCES = ("collection", "sealed_collection")


def _columns(conn: sqlite3.Connection, source: str) -> list[str]:
    """The columns the insert trigger ships, read from it so there is one list."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (f"holdings_outbox_{source}_insert",),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"holdings_outbox_{source}_insert trigger is missing")
    return re.findall(r"'(\w+)', NEW\.\w+", row[0].split("json_object(", 1)[1])


def shipped_columns(conn: sqlite3.Connection, source: str) -> list[str]:
    return _columns(conn, source)


def emit(conn: sqlite3.Connection, source: str | None = None) -> int:
    """Append an upsert for every current row of `source` (default: both).

    Returns the number of outbox rows written.  Runs in one transaction.
    """
    written = 0
    for src in [source] if source else SOURCES:
        if src not in SOURCES:
            raise ValueError(f"unknown holdings source {src!r}")
        cols = _columns(conn, src)
        obj = ", ".join(f"'{c}', {c}" for c in cols)
        cur = conn.execute(
            f"INSERT INTO holdings_outbox (source, row_id, op, payload) "
            f"SELECT '{src}', id, 'upsert', json_object({obj}) FROM {src} ORDER BY id"
        )
        written += cur.rowcount
    conn.commit()
    return written


def fold(conn: sqlite3.Connection) -> dict[str, dict[int, dict]]:
    """Reduce the log: per source, row_id -> payload of the latest op, deletes dropped."""
    rows = conn.execute("SELECT seq, source, row_id, op, payload FROM holdings_outbox")
    resolved = resolve(rows)
    return {s: resolved.get(s, {}) for s in SOURCES}


def current(conn: sqlite3.Connection) -> dict[str, dict[int, dict]]:
    """The holdings as the tables hold them now, in the shipped shape."""
    out: dict[str, dict[int, dict]] = {}
    for src in SOURCES:
        cols = _columns(conn, src)
        out[src] = {
            r[0]: dict(zip(cols, r))
            for r in conn.execute(f"SELECT {', '.join(cols)} FROM {src}")
        }
    return out
