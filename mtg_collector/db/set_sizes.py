"""Population of sets.base_set_size and sets.total_set_size.

Both columns exist because the base/boosterfun boundary cannot be derived from
the treatment columns -- see the comment on `sets` in schema.py.  They are
written at ingest and never at request time.

Two sources, both already in hand where they are read:

  * `total_set_size` <- Scryfall's per-set `card_count`, which `mtg cache all`
    fetches for every set and, before this, used transiently to size its
    backfill and then discarded.
  * `base_set_size` <- MTGJSON's `baseSetSize`, on every set object in
    AllPrintings.json, which `mtg data import` already iterates.

Everything here UPDATEs existing rows and never inserts.  A set that is not
cached locally is not a set the binder can render, and inventing a row for it
would put a set in the index with no printings behind it.  Nor does anything
here write NULL over a stored size: a source that has stopped reporting a
number has not told us the set shrank, and clearing the column would blank a
completion bar that was correct a moment ago.
"""

import sqlite3
from typing import Dict, Iterable, Optional

#: Rows per executemany + commit.  The prod DB is 11 GB and these run over ~993
#: sets, so the work is small -- the batching is here so a failure part-way
#: leaves committed, correct rows behind rather than one all-or-nothing
#: transaction held open across the whole catalogue.
BATCH_SIZE = 200


def _apply(conn: sqlite3.Connection, column: str, values, batch_size: int) -> int:
    """UPDATE one size column for many sets.  Returns the rows actually changed.

    The WHERE clause makes this idempotent in the strong sense: re-running with
    the same input writes nothing at all, so the returned count is "how much did
    this change", not "how many did I look at".
    """
    sql = (
        f"UPDATE sets SET {column} = ? "
        f"WHERE set_code = ? AND {column} IS NOT ?"
    )
    changed = 0
    batch = []
    for set_code, size in values:
        batch.append((size, set_code, size))
        if len(batch) >= batch_size:
            changed += _flush(conn, sql, batch)
            batch = []
    if batch:
        changed += _flush(conn, sql, batch)
    return changed


def _flush(conn: sqlite3.Connection, sql: str, batch) -> int:
    cursor = conn.executemany(sql, batch)
    conn.commit()
    return cursor.rowcount


def clean_size(raw) -> Optional[int]:
    """Coerce a reported size to a positive int, or None.

    Scryfall reports `card_count: 0` for a set announced but not yet spoiled.
    Zero is not a size, it is an absence, and storing it would make the UI
    render a 0/0 completion bar -- exactly the NaN the NULL case exists to
    avoid.
    """
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def apply_total_set_sizes(
    conn: sqlite3.Connection,
    scryfall_sets: Iterable[Dict],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Store Scryfall `card_count` as total_set_size.  Returns rows changed.

    `scryfall_sets` is the payload of Scryfall's /sets endpoint -- what
    `ScryfallBulkClient.get_all_sets()` returns.
    """
    values = []
    for entry in scryfall_sets:
        code = entry.get("code")
        if not code:
            continue
        size = clean_size(entry.get("card_count"))
        if size is None:
            continue
        values.append((code.lower(), size))
    return _apply(conn, "total_set_size", values, batch_size)


def apply_base_set_sizes(
    conn: sqlite3.Connection,
    mtgjson_sets: Dict[str, Dict],
    batch_size: int = BATCH_SIZE,
) -> int:
    """Store MTGJSON `baseSetSize` as base_set_size.  Returns rows changed.

    `mtgjson_sets` is AllPrintings.json's `data` object: set code -> set object.
    Sets AllPrintings does not carry keep whatever they had, which for most of
    them is NULL -- a permanent, legitimate value here.
    """
    values = []
    for set_code, set_data in mtgjson_sets.items():
        if not set_code:
            continue
        size = clean_size(set_data.get("baseSetSize"))
        if size is None:
            continue
        values.append((set_code.lower(), size))
    return _apply(conn, "base_set_size", values, batch_size)
