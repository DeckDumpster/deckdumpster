"""Backfill of the `sets` columns neither ingest path is guaranteed to have filled.

Two kinds of column live here, and they share this module because they share
one rule: everything below UPDATEs existing rows from a catalogue payload the
caller already holds, and nothing inserts.

  * **The sizes** -- `total_set_size` <- Scryfall's per-set `card_count`, and
    `base_set_size` <- MTGJSON's `baseSetSize`.  Both exist because the
    base/boosterfun boundary cannot be derived from the treatment columns --
    see the comment on `sets` in schema.py.
  * **The descriptors** -- `set_type`, `released_at`, `digital`, from the same
    Scryfall set object.  `mtg cache all` writes all three for every set it
    upserts, but a `sets` row is not evidence that it ever ran: `mtg data
    import` and the TCGCSV sealed importer both create stubs with
    `INSERT OR IGNORE INTO sets (set_code, set_name)`, and until de-22j
    `mtg cache set` skipped a set whose row already existed.  174 of the 192
    sets in the committed fixture carry NULL `released_at` for that reason,
    which is what makes `year:` match nothing on them, buckets them all at the
    bottom of the /sets index, and drops them from the deck builder's date
    filters.

Everything here UPDATEs existing rows and never inserts.  A set that is not
cached locally is not a set the binder can render, and inventing a row for it
would put a set in the index with no printings behind it.  Nor does anything
here write NULL over a stored value: a source that has stopped reporting a
number has not told us the set shrank, and clearing the column would blank a
completion bar that was correct a moment ago.  The same reading applies to a
descriptor -- an absent `released_at` is a payload we do not understand, not a
set that has un-released.
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


def clean_text(raw) -> Optional[str]:
    """Coerce a reported descriptor to a non-empty string, or None.

    An empty string is Scryfall not having a value for the field, and storing
    it would be worse than the NULL it replaced: `released_at IS NULL` is what
    the /sets index sorts on and what the deck builder's date filters test, and
    `''` passes both while meaning nothing.
    """
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def clean_flag(raw) -> Optional[int]:
    """Coerce Scryfall's `digital` boolean to 0/1, or None if not reported.

    The column is NOT NULL, so an unreported flag has to be skipped rather than
    written.  Unlike the other descriptors there is no reading it back to see
    whether it was ever populated -- a stub row's DEFAULT 0 and a paper set's
    stored 0 are the same byte -- which is why this writes the flag for every
    set the payload carries rather than only for rows that look unfilled.
    """
    if raw is None:
        return None
    return 1 if raw else 0


#: `sets` column -> how to read it out of a Scryfall set object.  Ordered as the
#: backfill reports them, and deliberately excluding `set_name`: it is NOT NULL
#: and every path that creates a stub row already writes the name it had.
_DESCRIPTORS = {
    "set_type": lambda entry: clean_text(entry.get("set_type")),
    "released_at": lambda entry: clean_text(entry.get("released_at")),
    "digital": lambda entry: clean_flag(entry.get("digital")),
}


def apply_set_metadata(
    conn: sqlite3.Connection,
    scryfall_sets: Iterable[Dict],
    batch_size: int = BATCH_SIZE,
) -> Dict[str, int]:
    """Store Scryfall set_type / released_at / digital.  Returns rows changed per column.

    `scryfall_sets` is the payload of Scryfall's /sets endpoint -- what
    `ScryfallBulkClient.get_all_sets()` returns, the same list the total size
    is read from, so a backfill pays for one request and writes four columns.

    The counts come back per column rather than summed because they answer
    different questions: `released_at` is the one the search and the index care
    about, and a run that repaired 174 release dates and flipped two digital
    flags should not report 176 of anything.
    """
    columns = {column: [] for column in _DESCRIPTORS}
    for entry in scryfall_sets:
        code = entry.get("code")
        if not code:
            continue
        code = code.lower()
        for column, read in _DESCRIPTORS.items():
            value = read(entry)
            if value is None:
                continue
            columns[column].append((code, value))
    return {
        column: _apply(conn, column, values, batch_size)
        for column, values in columns.items()
    }
