"""Generate tests/fixtures/test-data.sqlite for fast container UI tests.

Creates a fresh DB with current schema, caches printings for the sets needed by
demo data and UI test scenarios, optionally imports MTGJSON data (sealed products,
uuid map, booster data, sealed_product_cards), inserts fallback synthetic sealed
products, and VACUUMs.  Run once; commit the resulting ~20 MB file.  Re-run when
sets or sealed products need updating.

Usage:
    uv run python scripts/build_test_fixture.py
"""

import sqlite3
import uuid
from pathlib import Path

from mtg_collector.db.models import CardRepository, PrintingRepository, SetRepository
from mtg_collector.db.schema import init_db
from mtg_collector.services.scryfall import ScryfallAPI, ensure_set_cached
from mtg_collector.utils import now_iso

# Sets required by demo_data.py cards
DEMO_SETS = ["fdn", "dsk", "blb", "otj", "mh3", "spg", "woe", "lci", "mkm"]

# Extra sets required by UI test sealed-product scenarios
UI_TEST_SETS = ["ecl", "fin"]

# Sets required by demo ingest samples (recents page test data)
DEMO_INGEST_SETS = ["tsp", "ddh", "tmp", "8ed", "roe"]

ALL_SETS = DEMO_SETS + UI_TEST_SETS + DEMO_INGEST_SETS

# Fallback sealed products — inserted only if not already present from MTGJSON.
# The first 8 match demo_data.DEMO_SEALED_PRODUCTS category keywords so demo
# data load succeeds.  The last 2 match UI test scenario search terms.
SEALED_PRODUCTS = [
    # Demo data products (set_code, category, name)
    ("dsk", "booster_box", "Duskmourn: House of Horror Play Booster Box"),
    ("blb", "booster_box", "Bloomburrow Play Booster Box"),
    ("fdn", "booster_pack", "Foundations Play Booster Pack"),
    ("mh3", "booster_pack", "Modern Horizons 3 Play Booster Pack"),
    ("otj", "bundle", "Outlaws of Thunder Junction Bundle"),
    ("dsk", "bundle", "Duskmourn: House of Horror Bundle"),
    ("blb", "booster_pack", "Bloomburrow Play Booster Pack"),
    ("fdn", "booster_box", "Foundations Play Booster Box"),
    # UI test scenario products
    ("ecl", "collector_booster_omega_pack", "Lorwyn Eclipsed Collector Booster Omega Pack"),
    ("fin", "play_booster_box", "Final Fantasy Play Booster Box"),
]

OUTPUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "test-data.sqlite"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.unlink(missing_ok=True)

    print(f"==> Creating fixture DB at {OUTPUT}")

    conn = sqlite3.connect(str(OUTPUT))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    card_repo = CardRepository(conn)
    set_repo = SetRepository(conn)
    printing_repo = PrintingRepository(conn)

    api = ScryfallAPI()

    # Cache all required sets
    for set_code in ALL_SETS:
        print(f"  Caching set: {set_code.upper()}")
        ok = ensure_set_cached(api, set_code, card_repo, set_repo, printing_repo, conn)
        if not ok:
            print(f"    WARNING: Failed to cache {set_code.upper()}")

    # Import MTGJSON data if AllPrintings.json is available
    from mtg_collector.cli.data_cmd import get_allprintings_path, import_mtgjson
    if get_allprintings_path().exists():
        print("  Importing MTGJSON data (sealed products, uuid map, booster data)...")
        import_mtgjson(str(OUTPUT))
        # Trim MTGJSON tables to only the sets we need (keeps fixture small)
        conn2 = sqlite3.connect(str(OUTPUT))
        all_set_str = ",".join(f"'{s}'" for s in ALL_SETS)
        for table in ("mtgjson_printings", "mtgjson_uuid_map", "mtgjson_booster_sheets",
                       "mtgjson_booster_configs"):
            before = conn2.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            conn2.execute(f"DELETE FROM {table} WHERE set_code NOT IN ({all_set_str})")  # noqa: S608
            after = conn2.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            print(f"    Trimmed {table}: {before} -> {after}")
        # Trim sealed products and their cards to test sets only
        before = conn2.execute("SELECT COUNT(*) FROM sealed_products").fetchone()[0]
        conn2.execute(f"DELETE FROM sealed_products WHERE set_code NOT IN ({all_set_str})")  # noqa: S608
        after = conn2.execute("SELECT COUNT(*) FROM sealed_products").fetchone()[0]
        print(f"    Trimmed sealed_products: {before} -> {after}")
        # Clean up orphaned sealed_product_cards
        conn2.execute("""DELETE FROM sealed_product_cards WHERE sealed_product_uuid
                         NOT IN (SELECT uuid FROM sealed_products)""")
        remaining = conn2.execute("SELECT COUNT(*) FROM sealed_product_cards").fetchone()[0]
        print(f"    Remaining sealed_product_cards: {remaining}")
        conn2.commit()
        conn2.close()
    else:
        print("  WARNING: AllPrintings.json not found, skipping MTGJSON import")
        print("  Run 'mtg data fetch' first for full fixture with sealed product data")

    # Insert fallback sealed products (only if not already present from MTGJSON)
    ts = now_iso()
    existing_names = set()
    for row in conn.execute("SELECT name FROM sealed_products").fetchall():
        existing_names.add(row["name"])

    fallback_count = 0
    for set_code, category, name in SEALED_PRODUCTS:
        if name not in existing_names:
            conn.execute(
                """INSERT OR IGNORE INTO sealed_products
                   (uuid, name, set_code, category, imported_at, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), name, set_code, category, ts, "test_fixture"),
            )
            fallback_count += 1
    if fallback_count:
        print(f"  Inserted {fallback_count} fallback sealed products")

    # Seed price history for blb/124 (Artist's Talent) — used by collection_price_chart UI test
    print("  Seeding price data for UI tests...")
    price_rows = [
        ("blb", "124", "tcgplayer", "normal", 8.50, "2026-02-08"),
        ("blb", "124", "tcgplayer", "normal", 9.00, "2026-02-23"),
        ("blb", "124", "tcgplayer", "normal", 10.00, "2026-03-09"),
        ("blb", "124", "tcgplayer", "normal", 10.50, "2026-03-24"),
        ("blb", "124", "tcgplayer", "normal", 10.46, "2026-04-01"),
    ]
    for sc, cn, src, pt, price, observed in price_rows:
        conn.execute(
            "INSERT OR IGNORE INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sc, cn, src, pt, price, observed),
        )
    conn.execute(
        "INSERT OR REPLACE INTO latest_prices (set_code, collector_number, source, price_type, price, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("blb", "124", "tcgplayer", "normal", 10.46, "2026-04-01"),
    )
    print(f"  Seeded {len(price_rows)} price rows for blb/124")

    conn.commit()

    # Compact
    print("  VACUUM...")
    conn.execute("VACUUM")
    conn.close()

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"==> Done: {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
