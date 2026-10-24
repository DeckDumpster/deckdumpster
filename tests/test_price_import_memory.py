"""The price import streams MTGJSON documents instead of materialising them.

On 2026-10-24 the nightly import was OOM-killed at 12.5 GB RSS because
AllPrintings and AllPricesToday were each loaded whole. A tracemalloc peak is
deterministic where RSS and RLIMIT_AS are not, so this bounds the peak against
the size of a generated document: whole-document loading costs several times
the file, streaming costs a batch.
"""

import json
import sqlite3
import tracemalloc
from unittest.mock import patch

from mtg_collector.cli.data_cmd import import_prices
from mtg_collector.db.connection import close_connection
from mtg_collector.jsonstream import iter_object_members

N_UUIDS = 40_000
DATES = [f"2026-10-{d:02d}" for d in range(1, 11)]


def _write_fixtures(tmp_path):
    printings = tmp_path / "AllPrintings.json"
    prices = tmp_path / "AllPricesToday.json"
    sets = {}
    for s in range(40):
        sets[f"S{s:02d}"] = {
            "cards": [
                {"uuid": f"u{s * 1000 + i}", "number": str(i + 1), "pad": "x" * 200}
                for i in range(1000)
            ]
        }
    printings.write_text(json.dumps({"meta": {"v": 1}, "data": sets}))
    series = {d: 1.25 for d in DATES}
    data = {
        f"u{i}": {"paper": {
            "cardkingdom": {"retail": {"normal": series, "foil": series},
                            "buylist": {"normal": series}},
            "tcgplayer": {"retail": {"normal": series}},
        }}
        for i in range(N_UUIDS)
    }
    prices.write_text(json.dumps({"meta": {"v": 1}, "data": data}))
    return printings, prices


def test_import_prices_peak_memory_is_bounded(tmp_path):
    close_connection()
    printings, prices = _write_fixtures(tmp_path)
    doc_bytes = prices.stat().st_size + printings.stat().st_size
    db = str(tmp_path / "c.sqlite")

    tracemalloc.start()
    with patch("mtg_collector.cli.data_cmd.get_allpricestoday_path", return_value=prices), \
         patch("mtg_collector.cli.data_cmd.get_allprintings_path", return_value=printings):
        import_prices(db)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    conn.close()
    assert n == N_UUIDS * 4 * len(DATES)  # 4 series per uuid
    # json.load of both documents alone is several times their size on disk.
    assert peak < doc_bytes, f"peak {peak / 1e6:.0f} MB for {doc_bytes / 1e6:.0f} MB of JSON"


def test_stream_handles_chunk_boundaries_and_other_members(tmp_path):
    doc = {"meta": {"a": [1, 2, {"b": "}"}]}, "data": {f"k{i}": {"v": "é" * (i % 7), "n": i} for i in range(5000)},
           "tail": 12345}
    p = tmp_path / "d.json"
    p.write_text(json.dumps(doc, indent=1))
    with patch("mtg_collector.jsonstream._CHUNK", 37):
        with open(p) as f:
            got = dict(iter_object_members(f, "data"))
    assert got == doc["data"]
