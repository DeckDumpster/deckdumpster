"""One-time export of price and sealed price history into the lake, verified row for row.

Layout, under the destination URI (``s3://<lake>/lake/export`` in production, any
local directory in tests)::

    prices/observed_date=<D>/part.parquet
    sealed_prices/observed_date=<D>/part.parquet

One immutable file per observed date. Each is written once and never replaced
(the catalog role has no DeleteObject, and history for a past date does not
change); a rerun finds the file and *verifies* it instead. Verification reads
every file back and compares it to SQLite tuple for tuple, then compares the set
of dates, so an export is only ever reported done when the lake equals the table.

Prices are integer cents. A stored price that is not a whole number of cents
raises; the export never rounds history. ``price_type`` keeps the stored
vocabulary (``normal``, ``foil``, ``buylist_normal``, ``buylist_foil``) so the
export is lossless. ``uuid`` is the MTGJSON uuid for (set_code, collector_number)
— the smallest one when several share it — and NULL when unmapped.
"""

import sqlite3
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

PRICES_SCHEMA = pa.schema([
    ("uuid", pa.string()),
    ("set_code", pa.string()),
    ("collector_number", pa.string()),
    ("source", pa.string()),
    ("price_type", pa.string()),
    ("price_cents", pa.int64()),
    ("observed_date", pa.string()),
])

SEALED_PRICES_SCHEMA = pa.schema([
    ("tcgplayer_product_id", pa.string()),
    ("low_cents", pa.int64()),
    ("mid_cents", pa.int64()),
    ("high_cents", pa.int64()),
    ("market_cents", pa.int64()),
    ("direct_low_cents", pa.int64()),
    ("observed_date", pa.string()),
])

_PRICES_SQL = """
    SELECT (SELECT MIN(m.uuid) FROM mtgjson_uuid_map m
             WHERE m.set_code = p.set_code AND m.collector_number = p.collector_number),
           p.set_code, p.collector_number, p.source, p.price_type, p.price, p.observed_at
      FROM prices p
     WHERE p.observed_at = ?
     ORDER BY p.set_code, p.collector_number, p.source, p.price_type
"""

_SEALED_SQL = """
    SELECT tcgplayer_product_id, low_price, mid_price, high_price, market_price,
           direct_low_price, observed_at
      FROM sealed_prices
     WHERE observed_at = ?
     ORDER BY tcgplayer_product_id
"""


class ExportMismatch(Exception):
    """The lake does not equal the table."""


def cents(value):
    if value is None:
        return None
    c = round(value * 100)
    if abs(value * 100 - c) > 1e-6:
        raise ValueError(f"price {value!r} is not a whole number of cents")
    return c


def _prices_row(r):
    return (r[0], r[1], r[2], r[3], r[4], cents(r[5]), r[6])


def _sealed_row(r):
    return (r[0], *(cents(v) for v in r[1:6]), r[6])


@dataclass(frozen=True)
class _Dataset:
    name: str
    table: str
    schema: pa.Schema
    sql: str
    convert: object


DATASETS = (
    _Dataset("prices", "prices", PRICES_SCHEMA, _PRICES_SQL, _prices_row),
    _Dataset("sealed_prices", "sealed_prices", SEALED_PRICES_SCHEMA, _SEALED_SQL, _sealed_row),
)


def _filesystem(dest: str):
    """Return (filesystem, root path) for a local directory or ``s3://`` URI."""
    fs, root = pafs.FileSystem.from_uri(dest)
    return fs, root.rstrip("/")


def _exists(fs, path: str) -> bool:
    return fs.get_file_info(path).type == pafs.FileType.File


def _expected(conn: sqlite3.Connection, ds: _Dataset, date: str) -> list[tuple]:
    return [ds.convert(r) for r in conn.execute(ds.sql, (date,))]


def _read(fs, path: str, ds: _Dataset) -> list[tuple]:
    with fs.open_input_file(path) as f:
        table = pq.read_table(f, schema=ds.schema)
    cols = table.to_pydict()
    return list(zip(*(cols[n] for n in ds.schema.names)))


def _write(fs, path: str, ds: _Dataset, rows: list[tuple]):
    cols = list(zip(*rows)) if rows else [()] * len(ds.schema)
    table = pa.table(dict(zip(ds.schema.names, cols)), schema=ds.schema)
    fs.create_dir(path.rsplit("/", 1)[0], recursive=True)
    with fs.open_output_stream(path) as out:
        pq.write_table(table, out, compression="zstd")


def _dates(conn: sqlite3.Connection, ds: _Dataset) -> list[str]:
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT observed_at FROM {ds.table} ORDER BY observed_at")]


def _lake_dates(fs, root: str, ds: _Dataset) -> list[str]:
    infos = fs.get_file_info(pafs.FileSelector(f"{root}/{ds.name}", recursive=True, allow_not_found=True))
    prefix = "observed_date="
    return sorted(
        i.path.split("/")[-2][len(prefix):]
        for i in infos
        if i.type == pafs.FileType.File and i.path.endswith("/part.parquet")
    )


def export_history(conn: sqlite3.Connection, dest: str) -> dict:
    """Export every date of both tables, then verify the lake equals them.

    Returns ``{dataset: {"dates": n, "rows": n, "written": n}}``. Raises
    ``ExportMismatch`` on any disagreement; nothing is repaired or overwritten.
    """
    fs, root = _filesystem(dest)
    report = {}
    for ds in DATASETS:
        dates = _dates(conn, ds)
        rows_total = written = 0
        for date in dates:
            path = f"{root}/{ds.name}/observed_date={date}/part.parquet"
            expected = _expected(conn, ds, date)
            if _exists(fs, path):
                got = _read(fs, path, ds)
            else:
                _write(fs, path, ds, expected)
                written += 1
                got = _read(fs, path, ds)
            if got != expected:
                raise ExportMismatch(
                    f"{ds.name} {date}: lake has {len(got)} rows, table has {len(expected)}"
                    + ("" if len(got) != len(expected) else " (same count, different rows)")
                )
            rows_total += len(expected)
        lake_dates = _lake_dates(fs, root, ds)
        if lake_dates != dates:
            raise ExportMismatch(
                f"{ds.name}: lake dates differ from table dates: "
                f"only in lake {sorted(set(lake_dates) - set(dates))[:5]}, "
                f"only in table {sorted(set(dates) - set(lake_dates))[:5]}"
            )
        total = conn.execute(f"SELECT COUNT(*) FROM {ds.table}").fetchone()[0]
        if total != rows_total:
            raise ExportMismatch(f"{ds.name}: table holds {total} rows, verified {rows_total}")
        report[ds.name] = {"dates": len(dates), "rows": rows_total, "written": written}
    return report
