"""Offline collection valuation from the tenant zone (lakehouse 12, K5/K6).

    zone_holdings (state DB, folded from the encrypted zone)   x
    catalog.prices (Iceberg, whole history)                    =>
    collection_value_history per tenant

The series arithmetic is `db/growth.series_from_pop`, the same statements the
online route runs.  This module only supplies its two inputs from the lake: a
`pop_t` built from the zone's current holdings, and a `prices` table loaded from
Iceberg.  Cents survive the trip exactly (`price_cents / 100.0` is the double
nearest the dollar value the online table holds), so agreement is bit-for-bit
and `compare` accepts nothing looser.

Holdings are current state, which is what the zone's resolution rule produces:
a sold card has left the zone's `collection` rows' owned/ordered population and
so leaves the whole curve, and a missed night heals on the next run.

A tenant's value is only comparable to the online series when the zone holds
every holding change, so `compare_tenant` refuses a tenant with unshipped
outbox rows rather than reporting a difference the shipper explains.
"""

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass

from mtg_collector.db import growth

STATUSES = ("owned", "ordered")
CACHE_KIB = 65536
BATCH_ROWS = 50_000

_PRICES_SQL = """
CREATE TABLE prices (
    set_code TEXT NOT NULL, collector_number TEXT NOT NULL, source TEXT NOT NULL,
    price_type TEXT NOT NULL, price REAL NOT NULL, observed_at TEXT NOT NULL
);
"""
_PRICES_INDEX = (
    "CREATE INDEX idx_prices_key ON prices"
    "(set_code, collector_number, source, price_type, observed_at)"
)


class ValuationError(Exception):
    """The inputs cannot produce a series that means what the online one means."""


def open_work(shared_path: str) -> sqlite3.Connection:
    """The scratch database: the catalogue ATTACHed read-only for printings.

    It lives in an unlinked file, not in memory: the whole price history goes in it,
    and held in RAM that history alone reached the unit's 3 GiB MemoryMax.  The page
    cache is capped, so peak memory does not follow the history's size.
    """
    fd, path = tempfile.mkstemp(prefix="mtgc-value-")
    os.close(fd)
    conn = sqlite3.connect(path, uri=True)
    os.unlink(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute(f"PRAGMA cache_size = -{CACHE_KIB}")
    conn.execute("ATTACH DATABASE ? AS shared", (f"file:{shared_path}?mode=ro",))
    conn.executescript(_PRICES_SQL)
    return conn


def load_prices(conn: sqlite3.Connection, table) -> int:
    """Load the whole Iceberg price history into `prices`.  Returns rows loaded."""
    cols = ("set_code", "collector_number", "source", "price_type", "price_cents", "observed_date")
    n = 0
    for batch in table.scan(selected_fields=cols).to_arrow_batch_reader():
        for start in range(0, batch.num_rows, BATCH_ROWS):
            d = batch.slice(start, BATCH_ROWS).to_pydict()
            conn.executemany(
                "INSERT INTO prices VALUES (?,?,?,?,?,?)",
                ((d["set_code"][i], d["collector_number"][i], d["source"][i], d["price_type"][i],
                  d["price_cents"][i] / 100.0, d["observed_date"][i]) for i in range(len(d["set_code"]))),
            )
        n += batch.num_rows
        conn.commit()
    conn.execute(_PRICES_INDEX)
    return n


def holdings(state: sqlite3.Connection, database_id: str) -> list[dict]:
    """The tenant's `collection` holdings as the zone folded them."""
    return [json.loads(p) for (p,) in state.execute(
        "SELECT payload FROM zone_holdings WHERE database_id = ? AND source = 'collection'"
        " ORDER BY row_id", (database_id,))]


def series(conn: sqlite3.Connection, rows: list[dict], *, range_days: int = 0):
    """``(earliest, [(date, n, tcg_cents, ck_cents)])`` for one tenant's holdings."""
    growth._drop_temp_tables(conn)
    try:
        conn.execute("CREATE TEMP TABLE zone_h (printing_id TEXT, finish TEXT, acquired_at TEXT, status TEXT)")
        conn.executemany(
            "INSERT INTO zone_h VALUES (?,?,?,?)",
            [(r["printing_id"], r["finish"], r["acquired_at"], r["status"]) for r in rows])
        conn.execute(f"""
            CREATE TEMP TABLE pop_t AS
            SELECT p.set_code AS set_code, p.collector_number AS cn,
                   CASE WHEN h.finish IN ('foil', 'etched') THEN 'foil' ELSE 'normal' END AS price_type,
                   substr(h.acquired_at, 1, 10) AS acq_date
            FROM zone_h h JOIN shared.printings p ON p.printing_id = h.printing_id
            WHERE h.status IN {STATUSES!r} AND h.acquired_at IS NOT NULL""")
        unknown = conn.execute(
            f"SELECT COUNT(*) FROM zone_h h WHERE h.status IN {STATUSES!r} AND h.acquired_at IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM shared.printings p WHERE p.printing_id = h.printing_id)"
        ).fetchone()[0]
        if unknown:
            raise ValuationError(f"{unknown} held row(s) name a printing the catalogue does not hold")
        return growth.series_from_pop(conn, range_days=range_days)
    finally:
        growth._drop_temp_tables(conn)
        conn.execute("DROP TABLE IF EXISTS temp.zone_h")


@dataclass
class Comparison:
    database_id: str
    days_offline: int
    days_online: int
    differing: list  # (date, offline_row_or_None, online_row_or_None)

    @property
    def agree(self) -> bool:
        return not self.differing


def compare_rows(database_id, offline, online) -> Comparison:
    """Day-by-day equality of two ``(earliest, rows)`` results."""
    (e_off, r_off), (e_on, r_on) = offline, online
    a = {r[0]: tuple(r) for r in r_off}
    b = {r[0]: tuple(r) for r in r_on}
    diff = [(d, a.get(d), b.get(d)) for d in sorted(a.keys() | b.keys()) if a.get(d) != b.get(d)]
    if e_off != e_on:
        diff.insert(0, ("earliest", e_off, e_on))
    return Comparison(database_id, len(r_off), len(r_on), diff)


def pending(tenant: sqlite3.Connection, state: sqlite3.Connection, database_id: str) -> int:
    """Outbox rows the zone has not yet been shipped."""
    from mtg_collector.lake import shipper
    cur = shipper.cursor(state, database_id)
    return tenant.execute("SELECT COUNT(*) FROM holdings_outbox WHERE seq > ?", (cur,)).fetchone()[0]


def store(tenant: sqlite3.Connection, result) -> int:
    """Write the offline series as the tenant's stored history.  Returns days stored.

    The meta stamps are the tenant's own current revision and price import: once
    this is the only writer nothing reads them to decide staleness.
    """
    from mtg_collector.utils import now_iso

    earliest, rows = result
    through_d = growth.end_date(earliest) if earliest is not None else None
    rev, log_id = growth.collection_rev(tenant), growth.price_log_id(tenant)
    tenant.execute("DELETE FROM collection_value_history")
    tenant.executemany(
        "INSERT INTO collection_value_history (d, n, tcg_cents, ck_cents) VALUES (?,?,?,?)", rows)
    tenant.execute("DELETE FROM collection_value_history_meta")
    tenant.execute(
        "INSERT INTO collection_value_history_meta"
        " (id, built_at, collection_rev, price_log_id, earliest, through_d) VALUES (1,?,?,?,?,?)",
        (now_iso(), rev, log_id, earliest, through_d))
    tenant.commit()
    return len(rows)
