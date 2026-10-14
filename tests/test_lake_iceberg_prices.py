import sqlite3
from datetime import date

import pytest

from mtg_collector.lake import iceberg_prices as lake
from mtg_collector.lake.zone_guard import assert_clean


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE mtgjson_uuid_map (uuid TEXT, set_code TEXT, collector_number TEXT);
    CREATE TABLE prices (set_code TEXT, collector_number TEXT, source TEXT,
                         price_type TEXT, price REAL, observed_at TEXT);
    CREATE TABLE sealed_prices (tcgplayer_product_id TEXT, low_price REAL, mid_price REAL,
        high_price REAL, market_price REAL, direct_low_price REAL, observed_at TEXT);
    INSERT INTO mtgjson_uuid_map VALUES ('u-b','lci','1'),('u-a','lci','1'),('u-c','lci','2');
    INSERT INTO prices VALUES
      ('lci','1','tcgplayer','normal',1.005,'2026-10-09'),
      ('lci','1','cardkingdom','buylist_foil',0.5,'2026-10-09'),
      ('lci','2','tcgplayer','foil',3.0,'2026-10-10'),
      ('zzz','9','tcgplayer','foil',3.0,'2026-10-10');
    INSERT INTO sealed_prices VALUES ('55',1.0,2.0,NULL,1.5,0.25,'2026-10-10');
    """)
    return c


@pytest.fixture
def catalog(tmp_path):
    wh = tmp_path / "wh"
    wh.mkdir()
    return lake.open_catalog(str(tmp_path / "cat.sqlite"), f"file://{wh}")


def test_cents_and_uuid_resolution(conn):
    rows = lake.price_rows(conn)
    assert len(rows) == 3  # unmapped (zzz, 9) is not in the lake
    assert {r[0] for r in rows if r[1:3] == ("lci", "1")} == {"u-a"}
    assert lake.cents(1.005) == 100 and lake.cents(None) is None


def test_build_is_idempotent_and_verifies(conn, catalog):
    assert lake.build(conn, catalog) == {"prices": 3, "sealed_prices": 1}
    assert lake.build(conn, catalog) == {"prices": 0, "sealed_prices": 0}
    assert lake.verify(conn, catalog) == []


def test_build_lands_only_new_days(conn, catalog):
    lake.build(conn, catalog)
    conn.execute("INSERT INTO prices VALUES ('lci','2','tcgplayer','normal',2.0,'2026-10-11')")
    assert lake.build(conn, catalog)["prices"] == 1
    assert lake.verify(conn, catalog) == []


def test_verify_detects_drift(conn, catalog):
    lake.build(conn, catalog)
    conn.execute("UPDATE prices SET price = 9.0 WHERE price_type = 'foil' AND set_code='lci'")
    assert lake.verify(conn, catalog)


def test_age_alarm(conn, catalog):
    lake.build(conn, catalog)
    assert lake.check_age(catalog, date(2026, 10, 11)) == []
    assert lake.check_age(catalog, date(2026, 10, 20))


def test_empty_tables_are_stale(catalog):
    lake.ensure_tables(catalog)
    assert len(lake.check_age(catalog, date(2026, 10, 11))) == 2


def test_catalog_columns_pass_the_guard(catalog):
    lake.ensure_tables(catalog)
    tables = {i: [f.name for f in catalog.load_table(i).schema().fields]
              for i in (lake.PRICES, lake.SEALED_PRICES)}
    assert_clean(tables=tables)


def test_partitioned_on_observed_date(catalog):
    prices, _ = lake.ensure_tables(catalog)
    assert [f.name for f in prices.spec().fields] == ["observed_date"]
