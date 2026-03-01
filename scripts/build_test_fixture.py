"""Generate tests/fixtures/test-data.sqlite for fast container UI tests.

Creates a fresh DB with current schema, caches printings for the sets needed by
demo data and UI test scenarios, inserts synthetic sealed_products rows, and
VACUUMs.  Run once; commit the resulting ~20 MB file.  Re-run when sets or
sealed products need updating.

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

# Sets required by sample-ingest (recents page test data)
SAMPLE_INGEST_SETS = ["2ed", "eoe", "ice", "5dn", "ptc"]

ALL_SETS = DEMO_SETS + UI_TEST_SETS + SAMPLE_INGEST_SETS

# Synthetic sealed products.  The first 8 match demo_data.DEMO_SEALED_PRODUCTS
# category keywords so demo data load succeeds.  The last 2 match UI test
# scenario search terms.
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

    # Insert synthetic sealed products
    ts = now_iso()
    print(f"  Inserting {len(SEALED_PRODUCTS)} sealed products...")
    for set_code, category, name in SEALED_PRODUCTS:
        conn.execute(
            """INSERT OR IGNORE INTO sealed_products
               (uuid, name, set_code, category, imported_at, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), name, set_code, category, ts, "test_fixture"),
        )
    conn.commit()

    # Compact
    print("  VACUUM...")
    conn.execute("VACUUM")
    conn.close()

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"==> Done: {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
