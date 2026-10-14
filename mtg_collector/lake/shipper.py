"""Ship holdings to the tenant zone and read them back (lakehouse 11).

    tenant file: holdings_outbox (seq, source, row_id, op, payload)
         |  ship: contiguous seq range -> Parquet -> AES-256-GCM (lake/crypto.py)
         |        -> PUT tenant/database_id=<id>/dataset=holdings/as_of=<D>/part-seq-<a>-<b>.parquet.enc
         |        -> THEN advance the cursor
         v
    zone.sqlite (derived, rebuildable from the zone; not the registry):
         ship_cursor   per tenant, the last seq whose PUT succeeded
         ship_part     what was PUT
         ship_gap      a hole in the outbox seq run (a lost row), until resolved
         zone_part     what read-back opened
         zone_holdings the folded holdings, rebuilt from the zone alone
         |
    read-back: list the tenant's prefix, open every part, fold (lake/resolve.py)

Delivery is at-least-once.  The cursor moves only after the PUT returned, so a
crash between the two re-sends the range; the part is named for its range and
the cipher is deterministic, so the retry lands on the same object (or, on
another day, beside it with the same events), and the resolution rule makes a
doubled event change nothing.

A hole in the seq run -- an outbox row that should exist and does not -- means
a holding change was lost.  The shipper ships what is contiguous, records the
gap and reports it (exit 3); it never ships across one.  `resolve_gap` repairs
by re-emitting every current row and a delete for every zone row the table no
longer holds, so the fold is right again, then steps the cursor past the hole.

The three-number check (`check_tenant`): outbox rows up to the cursor, events
shipped, events read back.  Equal, with the fold of the outbox equal to
zone_holdings and no open gap, or the check fails.
"""

import io
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from mtg_collector.lake import crypto, holdings_outbox
from mtg_collector.lake import keys as lake_keys
from mtg_collector.lake import resolve as rs
from mtg_collector.utils import get_mtgc_home, now_iso

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PARTIAL = 2
EXIT_GAP = 3

BATCH = 5000

PART_SCHEMA = pa.schema([
    ("seq", pa.int64()),
    ("source", pa.string()),
    ("row_id", pa.int64()),
    ("op", pa.string()),
    ("payload", pa.string()),
])

STATE_SQL = """
CREATE TABLE IF NOT EXISTS ship_cursor (
    database_id TEXT PRIMARY KEY, shipped_through INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ship_part (
    key TEXT PRIMARY KEY, database_id TEXT NOT NULL,
    from_seq INTEGER NOT NULL, to_seq INTEGER NOT NULL, n_events INTEGER NOT NULL, put_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ship_gap (
    database_id TEXT NOT NULL, from_seq INTEGER NOT NULL, to_seq INTEGER NOT NULL,
    detected_at TEXT NOT NULL, resolved_at TEXT,
    PRIMARY KEY (database_id, from_seq)
);
CREATE TABLE IF NOT EXISTS zone_part (
    key TEXT PRIMARY KEY, database_id TEXT NOT NULL,
    from_seq INTEGER NOT NULL, to_seq INTEGER NOT NULL, n_events INTEGER NOT NULL, read_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zone_readback (
    database_id TEXT PRIMARY KEY, events_read INTEGER NOT NULL, read_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS zone_holdings (
    database_id TEXT NOT NULL, source TEXT NOT NULL, row_id INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (database_id, source, row_id)
);
CREATE TABLE IF NOT EXISTS ship_backfill (
    database_id TEXT PRIMARY KEY, rows_emitted INTEGER NOT NULL, emitted_at TEXT NOT NULL
);
"""

_PART_NAME = re.compile(r"/part-seq-(\d+)-(\d+)\.parquet\.enc$")


class ZoneError(Exception):
    """The zone, the outbox or the state disagree in a way no retry fixes."""


class ZoneIncomplete(ZoneError):
    """Read-back found seq ranges that were shipped (or should exist) and are not in the zone."""


def state_path():
    return get_mtgc_home() / "lake" / "zone.sqlite"


def open_state(path=None) -> sqlite3.Connection:
    path = path or state_path()
    if str(path) != ":memory:":
        path = str(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(STATE_SQL)
    return conn


class Zone:
    """The tenant zone's object store: a local directory in tests, s3:// in production."""

    def __init__(self, uri: str):
        self.fs, root = pafs.FileSystem.from_uri(uri)
        self.root = root.rstrip("/")

    def _p(self, key: str) -> str:
        return f"{self.root}/{key}" if self.root else key

    def put(self, key: str, blob: bytes) -> None:
        if self.root.startswith("/") or "/" in key:
            parent = self._p(key).rsplit("/", 1)[0]
            self.fs.create_dir(parent, recursive=True)
        with self.fs.open_output_stream(self._p(key)) as f:
            f.write(blob)

    def get(self, key: str) -> bytes:
        with self.fs.open_input_stream(self._p(key)) as f:
            return f.read()

    def delete(self, key: str) -> None:
        self.fs.delete_file(self._p(key))

    def list(self, prefix: str) -> list[str]:
        base = self._p(prefix).rstrip("/")
        infos = self.fs.get_file_info(pafs.FileSelector(base, recursive=True, allow_not_found=True))
        strip = len(self.root) + 1 if self.root else 0
        return sorted(i.path[strip:] for i in infos if i.type == pafs.FileType.File)


@dataclass
class ShipResult:
    database_id: str
    events: int = 0
    parts: int = 0
    gap: tuple[int, int] | None = None


@dataclass
class ReadbackResult:
    database_id: str
    parts: int = 0
    events: int = 0
    rows: int = 0


@dataclass
class Check:
    database_id: str
    outbox: int
    shipped: int
    read_back: int
    pending: int
    folded_equal: bool
    open_gaps: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.outbox == self.shipped == self.read_back
                and self.folded_equal and not self.open_gaps)


# --- cursor and gaps -------------------------------------------------------

def cursor(state: sqlite3.Connection, database_id: str) -> int:
    row = state.execute(
        "SELECT shipped_through FROM ship_cursor WHERE database_id = ?", (database_id,)
    ).fetchone()
    return row[0] if row else 0


def open_gaps(state: sqlite3.Connection, database_id: str) -> list[tuple[int, int]]:
    return state.execute(
        "SELECT from_seq, to_seq FROM ship_gap WHERE database_id = ? AND resolved_at IS NULL "
        "ORDER BY from_seq", (database_id,)
    ).fetchall()


def _record_gap(state, database_id, lo, hi):
    state.execute(
        "INSERT OR IGNORE INTO ship_gap (database_id, from_seq, to_seq, detected_at) VALUES (?,?,?,?)",
        (database_id, lo, hi, now_iso()),
    )


# --- ship ------------------------------------------------------------------

def _encode(events) -> bytes:
    cols = list(zip(*events))
    table = pa.table(
        {n: pa.array(list(c), type=t) for (n, t), c in zip(zip(PART_SCHEMA.names, PART_SCHEMA.types), cols)},
        schema=PART_SCHEMA,
    )
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()


def _decode(plain: bytes) -> list[tuple]:
    d = pq.read_table(io.BytesIO(plain), schema=PART_SCHEMA).to_pydict()
    return list(zip(d["seq"], d["source"], d["row_id"], d["op"], d["payload"]))


def ship_tenant(tenant: sqlite3.Connection, state: sqlite3.Connection, zone: Zone,
                database_id: str, lake_key: bytes, *, as_of: str, batch: int = BATCH) -> ShipResult:
    """Ship every contiguous outbox row past the cursor; stop at a gap."""
    result = ShipResult(database_id)
    while True:
        cur = cursor(state, database_id)
        rows = tenant.execute(
            "SELECT seq, source, row_id, op, payload FROM holdings_outbox "
            "WHERE seq > ? ORDER BY seq LIMIT ?", (cur, batch)
        ).fetchall()
        if not rows:
            return result
        want, run = cur + 1, []
        for r in rows:
            if r[0] != want:
                _record_gap(state, database_id, want, r[0] - 1)
                result.gap = (want, r[0] - 1)
                break
            run.append(r)
            want += 1
        if run:
            lo, hi = run[0][0], run[-1][0]
            key = rs.range_part_key(database_id, as_of, lo, hi)
            zone.put(key, crypto.seal(_encode(run), lake_key, key))
            state.execute("BEGIN IMMEDIATE")
            state.execute(
                "INSERT OR REPLACE INTO ship_part (key, database_id, from_seq, to_seq, n_events, put_at) "
                "VALUES (?,?,?,?,?,?)", (key, database_id, lo, hi, len(run), now_iso()))
            state.execute(
                "INSERT INTO ship_cursor (database_id, shipped_through, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(database_id) DO UPDATE SET shipped_through = excluded.shipped_through, "
                "updated_at = excluded.updated_at", (database_id, hi, now_iso()))
            state.execute("COMMIT")
            result.events += len(run)
            result.parts += 1
        if result.gap:
            return result


def resolve_gap(tenant: sqlite3.Connection, state: sqlite3.Connection, database_id: str) -> int:
    """Repair open gaps: append a delete for each zone row the table lacks and an
    upsert for each row it has, then step the cursor past the hole.

    Needs read-back to have opened everything shipped, so that zone_holdings is
    what the zone actually holds.  Returns the number of outbox rows appended.
    """
    gaps = open_gaps(state, database_id)
    if not gaps:
        return 0
    unread = state.execute(
        "SELECT COUNT(*) FROM ship_part p WHERE p.database_id = ? "
        "AND NOT EXISTS (SELECT 1 FROM zone_part z WHERE z.key = p.key)", (database_id,)
    ).fetchone()[0]
    if unread:
        raise ZoneError(f"{unread} shipped part(s) not yet read back; run read-back before resolving a gap")
    held = {
        (s, r) for s, r in state.execute(
            "SELECT source, row_id FROM zone_holdings WHERE database_id = ?", (database_id,))
    }
    now = holdings_outbox.current(tenant)
    live = {(s, r) for s, rows in now.items() for r in rows}
    tenant.execute("BEGIN IMMEDIATE")
    deleted = 0
    for source, row_id in sorted(held - live):
        tenant.execute(
            "INSERT INTO holdings_outbox (source, row_id, op, payload) VALUES (?, ?, 'delete', NULL)",
            (source, row_id))
        deleted += 1
    tenant.commit()
    emitted = holdings_outbox.emit(tenant)
    state.execute("BEGIN IMMEDIATE")
    for lo, hi in gaps:
        state.execute(
            "UPDATE ship_gap SET resolved_at = ? WHERE database_id = ? AND from_seq = ?",
            (now_iso(), database_id, lo))
    through = max(hi for _, hi in gaps)
    if through > cursor(state, database_id):
        state.execute(
            "INSERT INTO ship_cursor (database_id, shipped_through, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(database_id) DO UPDATE SET shipped_through = excluded.shipped_through, "
            "updated_at = excluded.updated_at", (database_id, through, now_iso()))
    state.execute("COMMIT")
    return deleted + emitted


def backfill(tenant: sqlite3.Connection, state: sqlite3.Connection, database_id: str, *, again=False) -> int:
    """Append every current row to the outbox, once.  Rows that predate the
    triggers are not in it; a second backfill needs `again`."""
    if not again and state.execute(
            "SELECT 1 FROM ship_backfill WHERE database_id = ?", (database_id,)).fetchone():
        raise ZoneError(f"{database_id} was already backfilled; pass again=True to emit a second time")
    n = holdings_outbox.emit(tenant)
    state.execute(
        "INSERT OR REPLACE INTO ship_backfill (database_id, rows_emitted, emitted_at) VALUES (?,?,?)",
        (database_id, n, now_iso()))
    return n


# --- read-back -------------------------------------------------------------

def _ranges_union(ranges):
    merged = []
    for lo, hi in sorted(ranges):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def _size(ranges) -> int:
    return sum(hi - lo + 1 for lo, hi in _ranges_union(ranges))


def readback_tenant(zone: Zone, state: sqlite3.Connection, database_id: str, lake_key: bytes) -> ReadbackResult:
    """Open every part under the tenant's holdings prefix and rebuild zone_holdings from them alone."""
    prefix = f"{rs.tenant_prefix(database_id)}dataset={rs.HOLDINGS_DATASET}/"
    events: dict[int, tuple] = {}
    parts = []
    for key in zone.list(prefix):
        m = _PART_NAME.search(key)
        if not m:
            raise ZoneError(f"unexpected object in the holdings prefix: {key}")
        if rs.database_id_of(key) != database_id:
            raise ZoneError(f"{key} is not {database_id}'s")
        lo, hi = int(m.group(1)), int(m.group(2))
        decoded = _decode(crypto.open_(zone.get(key), lake_key, key))
        if sorted(e[0] for e in decoded) != list(range(lo, hi + 1)):
            raise ZoneError(f"{key} does not carry exactly seq {lo}..{hi}")
        for e in decoded:
            if events.setdefault(e[0], e) != e:
                raise ZoneError(f"seq {e[0]} differs between parts of {database_id}")
        parts.append((key, lo, hi, len(decoded)))

    covered = _ranges_union([[lo, hi] for _, lo, hi, _ in parts])
    skipped = [[lo, hi] for lo, hi in state.execute(
        "SELECT from_seq, to_seq FROM ship_gap WHERE database_id = ?", (database_id,))]
    top = max((hi for _, hi in covered), default=0)
    need = [[1, top]] if top else []
    missing = _subtract(need, _ranges_union(covered + skipped))
    if missing:
        raise ZoneIncomplete(
            f"{database_id}: seq range(s) {', '.join(f'{a}-{b}' for a, b in missing)} "
            "are neither in the zone nor an accounted gap")

    folded = rs.resolve(sorted(events.values()))
    now = now_iso()
    state.execute("BEGIN IMMEDIATE")
    state.execute("DELETE FROM zone_holdings WHERE database_id = ?", (database_id,))
    state.execute("DELETE FROM zone_part WHERE database_id = ?", (database_id,))
    n_rows = 0
    for source, rows in folded.items():
        for row_id, payload in rows.items():
            state.execute(
                "INSERT INTO zone_holdings (database_id, source, row_id, payload) VALUES (?,?,?,?)",
                (database_id, source, row_id, json.dumps(payload, sort_keys=True)))
            n_rows += 1
    for key, lo, hi, n in parts:
        state.execute(
            "INSERT INTO zone_part (key, database_id, from_seq, to_seq, n_events, read_at) VALUES (?,?,?,?,?,?)",
            (key, database_id, lo, hi, n, now))
    state.execute(
        "INSERT OR REPLACE INTO zone_readback (database_id, events_read, read_at) VALUES (?,?,?)",
        (database_id, len(events), now))
    state.execute("COMMIT")
    return ReadbackResult(database_id, len(parts), len(events), n_rows)


def _subtract(need, have):
    out = []
    for lo, hi in need:
        at = lo
        for a, b in have:
            if b < at or a > hi:
                continue
            if a > at:
                out.append([at, a - 1])
            at = max(at, b + 1)
        if at <= hi:
            out.append([at, hi])
    return out


# --- the three-number check -----------------------------------------------

def check_tenant(tenant: sqlite3.Connection, state: sqlite3.Connection, database_id: str) -> Check:
    cur = cursor(state, database_id)
    outbox = tenant.execute("SELECT COUNT(*) FROM holdings_outbox WHERE seq <= ?", (cur,)).fetchone()[0]
    pending = tenant.execute("SELECT COUNT(*) FROM holdings_outbox WHERE seq > ?", (cur,)).fetchone()[0]
    shipped = _size(state.execute(
        "SELECT from_seq, to_seq FROM ship_part WHERE database_id = ?", (database_id,)).fetchall())
    row = state.execute(
        "SELECT events_read FROM zone_readback WHERE database_id = ?", (database_id,)).fetchone()
    read_back = row[0] if row else 0
    expect = rs.resolve(tenant.execute(
        "SELECT seq, source, row_id, op, payload FROM holdings_outbox WHERE seq <= ?", (cur,)))
    got: dict[str, dict[int, dict]] = {}
    for source, row_id, payload in state.execute(
            "SELECT source, row_id, payload FROM zone_holdings WHERE database_id = ?", (database_id,)):
        got.setdefault(source, {})[row_id] = json.loads(payload)
    return Check(database_id, outbox, shipped, read_back, pending, expect == got,
                 open_gaps(state, database_id))


# --- walking tenants -------------------------------------------------------

def active_ids(registry_conn) -> list[str]:
    return [r[0] for r in registry_conn.execute(
        "SELECT database_id FROM user WHERE retired_at IS NULL ORDER BY database_id")]


def run_all(registry_conn, state, zone, *, master: bytes, open_tenant, as_of: str,
            ids=None, do_ship=True, do_readback=True, out=print) -> int:
    """Ship then read back every active tenant.  Exit 3 on a gap, 2 if any tenant
    failed, else 0.  One tenant's failure never stops the others."""
    ids = ids or active_ids(registry_conn)
    failed, gapped = [], []
    for database_id in ids:
        try:
            try:
                key = lake_keys.lake_key(registry_conn, database_id, master)
            except lake_keys.KeyTombstoned:
                out(f"  [{database_id}] skipped: lake key tombstoned")
                continue
            tenant = open_tenant(database_id)
            try:
                if do_ship:
                    r = ship_tenant(tenant, state, zone, database_id, key, as_of=as_of)
                    out(f"  [{database_id}] shipped {r.events} event(s) in {r.parts} part(s)")
                    if r.gap:
                        gapped.append(database_id)
                        out(f"  [{database_id}] GAP: outbox seq {r.gap[0]}-{r.gap[1]} missing")
                if do_readback:
                    b = readback_tenant(zone, state, database_id, key)
                    out(f"  [{database_id}] read back {b.events} event(s), {b.rows} holding(s)")
            finally:
                tenant.close()
        except ZoneIncomplete as e:
            gapped.append(database_id)
            out(f"  [{database_id}] GAP in zone: {e}")
        except Exception as e:
            failed.append(database_id)
            out(f"  [{database_id}] FAILED: {type(e).__name__}: {e}")
    if gapped:
        return EXIT_GAP
    if failed:
        out(f"PARTIAL: {len(ids) - len(failed)}/{len(ids)} tenants; failed: {', '.join(failed)}")
        return EXIT_PARTIAL
    return EXIT_OK
