"""Offline valuation from the zone (lakehouse 12): row-identical to the online series."""

import datetime as dt
import json
import shutil
import sqlite3

import pytest

from mtg_collector.db import growth
from mtg_collector.db.schema import init_db
from mtg_collector.lake import holdings_outbox, shipper, valuation
from mtg_collector.lake import iceberg_prices as lake

_PRICE = ("INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at)"
          " VALUES (?,?,?,?,?,?)")
A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _day(offset):
    return (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=offset)).isoformat()


@pytest.fixture
def tenant(tmp_path):
    path = tmp_path / "t.sqlite"
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = OFF")
    init_db(c)
    c.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test')")
    for n in (1, 2, 3):
        c.execute("INSERT INTO cards (oracle_id, name) VALUES (?, ?)", (f"o{n}", f"Card {n}"))
        c.execute(
            "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes)"
            " VALUES (?,?,?,?, 'R', '[]')", (f"p{n}", f"o{n}", "tst", str(n)))
        c.execute("INSERT INTO mtgjson_uuid_map (uuid, set_code, collector_number) VALUES (?,?,?)",
                  (f"u{n}", "tst", str(n)))
    # prices begin before and inside the holding window; one card has none
    for off, tcg, ck in ((-30, 1.10, 0.90), (-10, 2.25, 1.75), (-2, 3.33, 2.01)):
        for n in (1, 2):
            c.execute(_PRICE, ("tst", str(n), "tcgplayer", "normal", round(tcg * n, 2), _day(off)))
            c.execute(_PRICE, ("tst", str(n), "cardkingdom", "normal", round(ck * n, 2), _day(off)))
        c.execute(_PRICE, ("tst", "1", "tcgplayer", "foil", round(tcg * 4, 2), _day(off)))
    for pid, fin, off, st in (("p1", "nonfoil", -20, "owned"), ("p1", "foil", -5, "ordered"),
                              ("p2", "nonfoil", -8, "owned"), ("p2", "nonfoil", -8, "sold"),
                              ("p3", "nonfoil", -1, "owned")):
        c.execute("INSERT INTO collection (printing_id, finish, acquired_at, source, status)"
                  " VALUES (?,?,?, 'manual', ?)", (pid, fin, f"{_day(off)}T12:00:00.000Z", st))
    c.commit()
    return c, str(path)


@pytest.fixture
def work_and_state(tenant, tmp_path):
    c, path = tenant
    wh = tmp_path / "wh"
    wh.mkdir()
    catalog = lake.open_catalog(str(tmp_path / "cat.sqlite"), f"file://{wh}")
    lake.build(c, catalog)
    shared = tmp_path / "shared.sqlite"
    shutil.copy(path, shared)
    work = valuation.open_work(str(shared))
    valuation.load_prices(work, catalog.load_table(lake.PRICES))
    state = shipper.open_state(":memory:")
    for source, rows in holdings_outbox.fold(c).items():
        for row_id, payload in rows.items():
            state.execute("INSERT INTO zone_holdings VALUES (?,?,?,?)", (A, source, row_id, json.dumps(payload)))
    return work, state


def test_offline_series_equals_online(tenant, work_and_state):
    c, _ = tenant
    work, state = work_and_state
    online = growth.series_rows(c, where_sql=growth.UNFILTERED_WHERE, params=[])
    offline = valuation.series(work, valuation.holdings(state, A))
    assert online[1] and any(r[2] for r in online[1])
    assert valuation.compare_rows(A, offline, online).agree
    assert offline == online


def test_compare_names_a_difference(tenant, work_and_state):
    c, _ = tenant
    work, state = work_and_state
    online = growth.series_rows(c, where_sql=growth.UNFILTERED_WHERE, params=[])
    state.execute("DELETE FROM zone_holdings WHERE row_id = 1 AND source = 'collection'")
    offline = valuation.series(work, valuation.holdings(state, A))
    cmp = valuation.compare_rows(A, offline, online)
    assert not cmp.agree and cmp.differing


def test_sold_card_leaves_the_whole_curve(tenant, work_and_state):
    work, state = work_and_state
    before = valuation.series(work, valuation.holdings(state, A))
    state.execute("UPDATE zone_holdings SET payload = json_set(payload, '$.status', 'sold')"
                  " WHERE source = 'collection' AND json_extract(payload, '$.printing_id') = 'p3'")
    after = valuation.series(work, valuation.holdings(state, A))
    assert before[1][-1][1] == after[1][-1][1] + 1


def test_empty_zone_is_an_empty_series(work_and_state):
    work, _ = work_and_state
    assert valuation.series(work, []) == (None, [])


def test_unknown_printing_is_refused(work_and_state):
    work, _ = work_and_state
    with pytest.raises(valuation.ValuationError):
        valuation.series(work, [{"printing_id": "nope", "finish": "nonfoil",
                                 "acquired_at": f"{_day(-1)}T00:00:00Z", "status": "owned"}])


def test_pending_outbox_blocks_comparison(tenant):
    c, _ = tenant
    state = shipper.open_state(":memory:")
    assert valuation.pending(c, state, A) > 0


def test_store_writes_the_series(tenant, work_and_state):
    c, _ = tenant
    work, state = work_and_state
    result = valuation.series(work, valuation.holdings(state, A))
    assert valuation.store(c, result) == len(result[1])
    assert growth.history_is_current(c)
    assert growth.read_history(c) == growth.payload(*growth.series_rows(
        c, where_sql=growth.UNFILTERED_WHERE, params=[]))


_PEAK_PROBE = """
import resource, sys
import pyarrow as pa
from mtg_collector.lake import valuation

rows = int(sys.argv[2])

class _Scan:
    def to_arrow_batch_reader(self):
        schema = pa.schema([("set_code", pa.string()), ("collector_number", pa.string()),
                            ("source", pa.string()), ("price_type", pa.string()),
                            ("price_cents", pa.int64()), ("observed_date", pa.string())])
        def gen():
            step = 100_000
            for lo in range(0, rows, step):
                ids = range(lo, min(lo + step, rows))
                yield pa.record_batch([
                    pa.array(["s%d" % (i % 900) for i in ids]), pa.array(["%d" % (i % 400) for i in ids]),
                    pa.array(["tcgplayer"] * len(ids)), pa.array(["normal"] * len(ids)),
                    pa.array([i % 5000 for i in ids], pa.int64()),
                    pa.array(["2026-01-%02d" % (1 + i % 28) for i in ids])], schema=schema)
        return pa.RecordBatchReader.from_batches(schema, gen())

class _Table:
    def scan(self, selected_fields):
        return _Scan()

work = valuation.open_work(sys.argv[1])
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
assert valuation.load_prices(work, _Table()) == rows
print((resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before) // 1024)
"""

PEAK_GROWTH_BOUND_MIB = 80


def test_price_load_memory_is_bounded_at_ten_times_the_history(tmp_path):
    import subprocess
    import sys
    shared = tmp_path / "shared.sqlite"
    sqlite3.connect(shared).close()
    out = subprocess.run([sys.executable, "-c", _PEAK_PROBE, str(shared), "1000000"],
                         capture_output=True, text=True, check=True)
    assert int(out.stdout.strip().splitlines()[-1]) < PEAK_GROWTH_BOUND_MIB
