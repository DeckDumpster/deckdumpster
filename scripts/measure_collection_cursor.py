"""Re-measure deep-window cost on a 110,018-printing catalogue: OFFSET vs cursor.

Synthetic rows, real schema and handler. Prints one line per depth.
    uv run python scripts/measure_collection_cursor.py
"""

import os
import sqlite3
import tempfile
import time

from mtg_collector.db.schema import init_db
from mtg_collector.tenancy import SingleTenantResolver, bind
from tests.test_collection_totals import _call

PRINTINGS, OWNED = 110_018, 15_045


def build(path):
    conn = sqlite3.connect(path)
    init_db(conn)
    conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'T')")
    conn.executemany(
        "INSERT INTO cards (oracle_id, name, color_identity) VALUES (?, ?, '[]')",
        ((f"o{i}", f"Card {i // 3:06d}") for i in range(PRINTINGS)),
    )
    conn.executemany(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes, card_name) "
        "VALUES (?, ?, 'tst', ?, 'rare', '[\"nonfoil\"]', ?)",
        ((f"p{i}", f"o{i}", str(i), f"Card {i // 3:06d}") for i in range(PRINTINGS)),
    )
    conn.executemany(
        "INSERT INTO collection (printing_id, finish, acquired_at, source, status, card_name) "
        "VALUES (?, 'nonfoil', '2025-01-01T00:00:00.000Z', 'manual', 'owned', ?)",
        ((f"p{i * 7}", f"Card {i * 7 // 3:06d}") for i in range(OWNED)),
    )
    conn.commit()
    conn.close()


def timed(db, **p):
    t = time.perf_counter()
    body = _call(db, {"limit": 250, **p})
    return (time.perf_counter() - t) * 1000, body


with bind(SingleTenantResolver().resolve(None)), tempfile.TemporaryDirectory() as d:
    db = os.path.join(d, "m.sqlite")
    build(db)
    for q in ({"q": "is:unowned"}, {}):
        for depth in (0, 5_000, 14_000, 50_000, 90_000):
            if q == {} and depth > OWNED - 800:
                continue
            ms_off, _ = timed(db, **q, offset=depth, known_total=PRINTINGS)
            if depth:
                cur = _call(db, {**q, "limit": 1, "offset": depth - 1})["next_cursor"]
                ms_cur, _ = timed(db, **q, cursor=cur)
            else:
                ms_cur = ms_off
            print(f"{q or 'owned'} depth={depth:>7} offset={ms_off:8.1f} ms  cursor={ms_cur:8.1f} ms")
raise SystemExit(1)  # tmp: surfaces output via the red tail
