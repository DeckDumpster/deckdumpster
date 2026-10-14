"""Copy a table between attached databases by column name, never by position (sp-63y52k).

`INSERT INTO dst.t SELECT * FROM src.t` pairs columns by position. A deployed
database grew its tables with ALTER TABLE ADD COLUMN, which appends, while a
fresh `init_db` declares each column where the schema text puts it. Prod's
`sets` reads (..., cards_fetched_at, digital, ...) and a fresh one
(..., digital, cards_fetched_at, ...): a positional copy swaps the two, and the
37 sets with a NULL cards_fetched_at fail `NOT NULL constraint failed:
sets.digital`. Naming the columns makes column order irrelevant.

Rules, all loud:
  - a source column the destination lacks is refused (a by-name copy would drop it);
  - a destination column the source lacks takes its declared default; NOT NULL
    with no default is refused;
  - a NULL in a destination NOT NULL column takes the declared default, and the
    count of substituted rows is returned so the caller reports it; with no
    default it is refused.
"""

import sqlite3
from dataclasses import dataclass, field


class TableCopyError(Exception):
    """The source table cannot be copied into the destination schema without losing data."""


@dataclass
class CopyResult:
    table: str
    source_rows: int
    copied_rows: int
    # column -> (rows whose NULL took the default, the default's SQL text)
    defaulted: dict = field(default_factory=dict)
    # destination columns the source does not have (filled by their declared default)
    absent: list = field(default_factory=list)


def _columns(conn, schema, table):
    return [
        (r[1], bool(r[3]), r[4])
        for r in conn.execute(f"PRAGMA {schema}.table_xinfo([{table}])")
        if r[6] == 0
    ]


def copy_table(conn: sqlite3.Connection, src: str, dst: str, table: str) -> CopyResult:
    """Replace `dst.table`'s rows with `src.table`'s, matched by column name."""
    dcols = _columns(conn, dst, table)
    scols = {name for name, _, _ in _columns(conn, src, table)}
    dnames = {name for name, _, _ in dcols}
    extra = sorted(scols - dnames)
    if extra:
        raise TableCopyError(f"{table}: source column(s) {extra} have no destination column")
    result = CopyResult(table, conn.execute(f"SELECT COUNT(*) FROM {src}.[{table}]").fetchone()[0], 0)
    names, exprs = [], []
    for name, notnull, dflt in dcols:
        if name not in scols:
            if notnull and dflt is None:
                raise TableCopyError(f"{table}.{name}: NOT NULL with no default and absent from the source")
            result.absent.append(name)
            continue
        names.append(f"[{name}]")
        if notnull:
            nulls = conn.execute(
                f"SELECT COUNT(*) FROM {src}.[{table}] WHERE [{name}] IS NULL").fetchone()[0]
            if nulls:
                if dflt is None:
                    raise TableCopyError(
                        f"{table}.{name}: {nulls} source row(s) NULL, and the column is NOT NULL with no default")
                result.defaulted[name] = (nulls, dflt)
                exprs.append(f"COALESCE([{name}], {dflt})")
                continue
        exprs.append(f"[{name}]")
    conn.execute(f"DELETE FROM {dst}.[{table}]")
    conn.execute(
        f"INSERT INTO {dst}.[{table}] ({', '.join(names)}) SELECT {', '.join(exprs)} FROM {src}.[{table}]")
    result.copied_rows = conn.execute(f"SELECT COUNT(*) FROM {dst}.[{table}]").fetchone()[0]
    if result.copied_rows != result.source_rows:
        raise TableCopyError(f"{table}: copied {result.copied_rows} of {result.source_rows} rows")
    return result


def describe(r: CopyResult) -> str:
    """One line per table: `<table> <source> -> <copy>` plus anything that was not a verbatim copy."""
    line = f"{r.table} {r.source_rows} -> {r.copied_rows}"
    for col, (n, dflt) in r.defaulted.items():
        line += f"; {r.table}.{col}: {n} NULL row(s) took the declared default {dflt}"
    if r.absent:
        line += f"; absent in source, declared default used: {r.absent}"
    return line
