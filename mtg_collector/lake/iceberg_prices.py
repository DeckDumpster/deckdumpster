"""Iceberg v2 price tables on PyIceberg's SQL catalog (K2).

The catalog is a SQLite file on the data volume (Litestream replicates it like
the registry) and the data is Parquet, so a later move to Nessie or a REST
catalog is a catalog migration and not a data migration.

    catalog.prices(uuid, set_code, collector_number, source, price_type,
                   price_cents, observed_date)         identity-partitioned on observed_date
    catalog.sealed_prices(tcgplayer_product_id, low_cents, mid_cents, high_cents,
                          market_cents, direct_low_cents, observed_date)

`price_type` is the stored value: normal / foil, with a `buylist_` prefix for
Card Kingdom's buylist.  The build is per day and append-only: a day already in
the table is never rewritten, so a rerun lands nothing new.  pyiceberg and
pyarrow are imported where used so the pure helpers (and the guard) stay
importable without them.
"""

import sqlite3
from datetime import date

NAMESPACE = "catalog"
PRICES = f"{NAMESPACE}.prices"
SEALED_PRICES = f"{NAMESPACE}.sealed_prices"

PRICES_COLUMNS = (
    "uuid", "set_code", "collector_number", "source", "price_type",
    "price_cents", "observed_date",
)
SEALED_COLUMNS = (
    "tcgplayer_product_id", "low_cents", "mid_cents", "high_cents",
    "market_cents", "direct_low_cents", "observed_date",
)
SOURCES = ("tcgplayer", "cardkingdom")
MAX_AGE_DAYS = 3
_APPEND_ROWS = 250_000


def cents(value):
    return None if value is None else round(value * 100)


def open_catalog(catalog_path: str, warehouse: str):
    from pyiceberg.catalog.sql import SqlCatalog

    return SqlCatalog(
        "mtgc", uri=f"sqlite:///{catalog_path}", warehouse=warehouse,
    )


def _schemas():
    from pyiceberg.partitioning import PartitionField, PartitionSpec
    from pyiceberg.schema import Schema
    from pyiceberg.transforms import IdentityTransform
    from pyiceberg.types import LongType, NestedField, StringType

    def s(i, n, req=True):
        return NestedField(i, n, StringType(), required=req)

    prices = Schema(
        s(1, "uuid"), s(2, "set_code"), s(3, "collector_number"), s(4, "source"),
        s(5, "price_type"), NestedField(6, "price_cents", LongType(), required=True),
        s(7, "observed_date"),
    )
    sealed = Schema(
        s(1, "tcgplayer_product_id"),
        *(NestedField(i, n, LongType(), required=False)
          for i, n in enumerate(SEALED_COLUMNS[1:6], start=2)),
        s(7, "observed_date"),
    )

    def spec():
        return PartitionSpec(PartitionField(
            source_id=7, field_id=1000, transform=IdentityTransform(), name="observed_date"))

    return prices, sealed, spec


def ensure_tables(catalog):
    catalog.create_namespace_if_not_exists(NAMESPACE)
    prices, sealed, spec = _schemas()
    return (
        catalog.create_table_if_not_exists(
            PRICES, schema=prices, partition_spec=spec(), properties={"format-version": "2"}),
        catalog.create_table_if_not_exists(
            SEALED_PRICES, schema=sealed, partition_spec=spec(), properties={"format-version": "2"}),
    )


def _in_clause(column, dates):
    dates = sorted(dates)
    return f"WHERE {column} IN ({','.join('?' * len(dates))})", dates


def iter_price_rows(conn: sqlite3.Connection, dates=None):
    """prices joined to one uuid per (set_code, collector_number): the lowest.

    `dates` None means every day; an empty collection means none.  Rows are
    yielded from the cursor, never collected: the table holds every day ever
    imported and a list of them is what outgrew the chain's memory cap.
    """
    if dates is not None and not dates:
        return
    where, args = _in_clause("p.observed_at", dates) if dates is not None else ("", [])
    cur = conn.execute(
        f"""SELECT m.uuid, p.set_code, p.collector_number, p.source, p.price_type,
                   p.price, p.observed_at
            FROM prices p
            JOIN (SELECT set_code, collector_number, MIN(uuid) AS uuid
                  FROM mtgjson_uuid_map GROUP BY set_code, collector_number) m
              ON m.set_code = p.set_code AND m.collector_number = p.collector_number
            {where}
            ORDER BY p.observed_at, p.set_code, p.collector_number, p.source, p.price_type""",
        args,
    )
    for r in cur:
        yield (*r[:5], cents(r[5]), r[6])


def iter_sealed_rows(conn: sqlite3.Connection, dates=None):
    if dates is not None and not dates:
        return
    where, args = _in_clause("observed_at", dates) if dates is not None else ("", [])
    cur = conn.execute(
        f"""SELECT tcgplayer_product_id, low_price, mid_price, high_price,
                   market_price, direct_low_price, observed_at
            FROM sealed_prices {where} ORDER BY observed_at, tcgplayer_product_id""",
        args,
    )
    for r in cur:
        yield (r[0], *map(cents, r[1:6]), r[6])


def price_rows(conn: sqlite3.Connection, dates=None):
    return list(iter_price_rows(conn, dates))


def _arrow(columns, rows, table):
    import pyarrow as pa

    return pa.Table.from_pydict(
        {c: [r[i] for r in rows] for i, c in enumerate(columns)},
        schema=table.schema().as_arrow(),
    )


def _lake_dates(table) -> set[str]:
    dates = set()
    for batch in table.scan(selected_fields=("observed_date",)).to_arrow_batch_reader():
        dates.update(batch.column("observed_date").unique().to_pylist())
    return dates


def _sqlite_dates(conn, which: str) -> set[str]:
    return {r[0] for r in conn.execute(f"SELECT DISTINCT observed_at FROM {which}")}


def _day_batches(rows, chunk=_APPEND_ROWS):
    """Chunks of at most `chunk` rows from an ordered row stream."""
    buf = []
    for r in rows:
        buf.append(r)
        if len(buf) >= chunk:
            yield buf
            buf = []
    if buf:
        yield buf


def build(conn: sqlite3.Connection, catalog) -> dict[str, int]:
    """Append every day SQLite holds and the lake does not.  Returns rows landed.

    One day at a time, in chunks: the working set is a chunk of rows, not the
    backlog.  A first build with an empty lake lands every day ever imported.
    """
    prices, sealed = ensure_tables(catalog)
    landed = {}
    for name, table, which, columns, fetch in (
        ("prices", prices, "prices", PRICES_COLUMNS, iter_price_rows),
        ("sealed_prices", sealed, "sealed_prices", SEALED_COLUMNS, iter_sealed_rows),
    ):
        n = 0
        for day in sorted(_sqlite_dates(conn, which) - _lake_dates(table)):
            for chunk in _day_batches(fetch(conn, [day])):
                table.append(_arrow(columns, chunk, table))
                n += len(chunk)
        landed[name] = n
    return landed


def newest_date(table) -> str | None:
    dates = _lake_dates(table)
    return max(dates) if dates else None


def age_days(table, today: date) -> int | None:
    newest = newest_date(table)
    return None if newest is None else (today - date.fromisoformat(newest)).days


def check_age(catalog, today: date, max_days: int = MAX_AGE_DAYS) -> list[str]:
    """Problems, empty when both tables are fresh.  An empty table is stale."""
    problems = []
    for ident in (PRICES, SEALED_PRICES):
        age = age_days(catalog.load_table(ident), today)
        if age is None:
            problems.append(f"{ident} is empty")
        elif age > max_days:
            problems.append(f"{ident} newest day is {age} days old (max {max_days})")
    return problems


def _lake_summary(table, value_columns):
    import pyarrow as pa

    out: dict[str, list[int]] = {}
    scan = table.scan(selected_fields=("observed_date", *value_columns))
    for batch in scan.to_arrow_batch_reader():
        grouped = pa.Table.from_batches([batch]).group_by("observed_date").aggregate(
            [([], "count_all")] + [(c, "sum") for c in value_columns])
        for row in grouped.to_pylist():
            acc = out.setdefault(row["observed_date"], [0] * (len(value_columns) + 1))
            acc[0] += row["count_all"]
            for i, c in enumerate(value_columns, start=1):
                acc[i] += row[f"{c}_sum"] or 0
    return out


def _sqlite_summary(rows, n_value_cols, first_value_idx):
    out: dict[str, list[int]] = {}
    for r in rows:
        acc = out.setdefault(r[-1], [0] * (n_value_cols + 1))
        acc[0] += 1
        for i in range(n_value_cols):
            acc[i + 1] += r[first_value_idx + i] or 0
    return out


def verify(conn: sqlite3.Connection, catalog) -> list[str]:
    """Per day, the lake's row count and cent total must equal SQLite's.

    SQLite rows that cannot map to a uuid are not in the lake, so the comparison
    is made on the same joined rows `build` reads.
    """
    prices, sealed = (catalog.load_table(PRICES), catalog.load_table(SEALED_PRICES))
    checks = (
        (PRICES, _lake_summary(prices, ["price_cents"]),
         _sqlite_summary(iter_price_rows(conn), 1, 5)),
        (SEALED_PRICES,
         _lake_summary(sealed, list(SEALED_COLUMNS[1:6])),
         _sqlite_summary(iter_sealed_rows(conn), 5, 1)),
    )
    problems = []
    for ident, lake, db in checks:
        for day in sorted(set(lake) | set(db)):
            if lake.get(day) != db.get(day):
                problems.append(f"{ident} {day}: lake {lake.get(day)} != sqlite {db.get(day)}")
    return problems
