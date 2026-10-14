"""One-time price history export: lake must equal the tables, row for row."""

import sqlite3

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.lake.price_export import ExportMismatch, export_history


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    c.execute("INSERT INTO mtgjson_uuid_map VALUES ('u-b','lci','1'),('u-a','lci','1'),('u-c','lci','2')")
    c.executemany(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) VALUES (?,?,?,?,?,?)",
        [
            ("lci", "1", "tcgplayer", "normal", 1.25, "2026-01-01"),
            ("lci", "1", "cardkingdom", "buylist_foil", 0.1, "2026-01-01"),
            ("lci", "2", "tcgplayer", "foil", 3.0, "2026-01-02"),
            ("zzz", "9", "tcgplayer", "normal", 0.07, "2026-01-02"),
        ],
    )
    c.executemany(
        "INSERT INTO sealed_prices (tcgplayer_product_id, low_price, market_price, observed_at) VALUES (?,?,?,?)",
        [("111", 10.5, None, "2026-01-01"), ("222", 99.99, 101.0, "2026-01-02")],
    )
    c.commit()
    return c


def test_export_verifies_and_is_idempotent(conn, tmp_path):
    first = export_history(conn, str(tmp_path))
    assert first["prices"] == {"dates": 2, "rows": 4, "written": 2}
    assert first["sealed_prices"] == {"dates": 2, "rows": 2, "written": 2}
    again = export_history(conn, str(tmp_path))
    assert again["prices"]["written"] == 0 and again["sealed_prices"]["written"] == 0


def test_uuid_is_smallest_mapped_or_null(conn, tmp_path):
    import pyarrow.parquet as pq
    export_history(conn, str(tmp_path))
    rows = pq.ParquetFile(tmp_path / "prices" / "observed_date=2026-01-01" / "part.parquet").read().to_pylist()
    assert {r["uuid"] for r in rows} == {"u-a"}
    rows = pq.ParquetFile(tmp_path / "prices" / "observed_date=2026-01-02" / "part.parquet").read().to_pylist()
    assert {r["set_code"]: r["uuid"] for r in rows} == {"lci": "u-c", "zzz": None}
    assert {r["price_cents"] for r in rows} == {300, 7}


def test_changed_table_after_export_is_a_mismatch(conn, tmp_path):
    export_history(conn, str(tmp_path))
    conn.execute(
        "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES ('lci','3','tcgplayer','normal',1.0,'2026-01-01')")
    with pytest.raises(ExportMismatch):
        export_history(conn, str(tmp_path))


def test_tampered_lake_file_is_a_mismatch(conn, tmp_path):
    export_history(conn, str(tmp_path))
    conn.execute("UPDATE prices SET price = 9.0 WHERE set_code='zzz'")
    with pytest.raises(ExportMismatch):
        export_history(conn, str(tmp_path))


def test_extra_lake_date_is_a_mismatch(conn, tmp_path):
    export_history(conn, str(tmp_path))
    conn.execute("DELETE FROM sealed_prices WHERE observed_at='2026-01-02'")
    with pytest.raises(ExportMismatch):
        export_history(conn, str(tmp_path))


def test_fractional_cent_raises(conn, tmp_path):
    conn.execute("UPDATE prices SET price = 1.234 WHERE set_code='zzz'")
    with pytest.raises(ValueError):
        export_history(conn, str(tmp_path))
