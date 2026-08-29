"""Generate tests/fixtures/test-data.sqlite for fast container UI tests.

Creates a fresh DB with current schema, caches printings for the sets needed by
demo data and UI test scenarios, optionally imports MTGJSON data (sealed products,
uuid map, booster data, sealed_product_cards), inserts fallback synthetic sealed
products, and VACUUMs.  Run once; commit the resulting ~20 MB file.  Re-run when
sets or sealed products need updating.

Usage:
    uv run python scripts/build_test_fixture.py
"""

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from mtg_collector.cli.demo_data import DEMO_CARDS
from mtg_collector.db.models import CardRepository, PrintingRepository, SetRepository
from mtg_collector.db.schema import init_db, refresh_latest_prices
from mtg_collector.db.set_sizes import apply_base_set_sizes
from mtg_collector.services.scryfall import ScryfallAPI, ensure_set_cached
from mtg_collector.utils import now_iso

# Sets required by demo_data.py cards
DEMO_SETS = ["fdn", "dsk", "blb", "otj", "mh3", "spg", "woe", "lci", "mkm"]

# Extra sets required by UI test sealed-product scenarios
UI_TEST_SETS = ["ecl", "fin"]

# Sets required by demo ingest samples (recents page test data)
DEMO_INGEST_SETS = ["tsp", "ddh", "tmp", "8ed", "roe"]

# Sets required by the precon / Jumpstart import picker UI tests
# (mtgjson_decks rows + sets table entries for friendly names).
PRECON_TEST_SETS = ["j25", "spm"]

ALL_SETS = DEMO_SETS + UI_TEST_SETS + DEMO_INGEST_SETS + PRECON_TEST_SETS

# MTGJSON `baseSetSize` for every set above, keyed the way AllPrintings.json
# keys its `data` object.
#
# The other half of the pair needs no table here: `ensure_set_cached` already
# stores Scryfall's `card_count` as total_set_size for every set it caches
# (de-igx), so total_set_size lands on its own and stays current with whatever
# Scryfall reports the day the fixture is rebuilt.  base_set_size has no such
# source -- it is only in AllPrintings.json, a 537 MB download the fixture
# builder should not need -- and without it every set in the fixture is one
# contiguous run, so neither the completion meters on /sets nor the
# base | extended | promo split on /sets/:set_code can be reached from a
# --test container at all (de-1ov).
#
# SPG is here with 0 deliberately.  MTGJSON reports `baseSetSize: 0` for
# Special Guests, `clean_size()` reads 0 as an absence rather than a size, and
# the row is left NULL -- so the fixture keeps exactly one cached set in the
# permanent, legitimate NULL state the hidden-meter path exists for.  Do not
# "fix" it to a positive number: the fixture would then have nothing to test
# that path against.
FIXTURE_BASE_SET_SIZES = {
    "8ED": 350,
    "BLB": 281,
    "DDH": 80,
    "DSK": 286,
    "ECL": 408,
    "FDN": 291,
    "FIN": 309,
    "J25": 779,
    "LCI": 291,
    "MH3": 303,
    "MKM": 286,
    "OTJ": 286,
    "ROE": 248,
    "SPG": 0,
    "SPM": 198,
    "TMP": 350,
    "TSP": 301,
    "WOE": 276,
}

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

# Sealed price seeding.
#
# The /sealed page shows a per-unit market price alongside a quantity x price
# total, so the fixture needs prices on the products demo data actually holds —
# including one with quantity > 1 — for that arithmetic to be exercisable.
#
# CRITICAL: the latest_sealed_prices VIEW filters on a GLOBAL max observed_at
# (WHERE observed_at = (SELECT MAX(observed_at) FROM sealed_prices)), not a
# per-product max — see efj-mtgc-gyp. Every row seeded here MUST therefore share
# one observed_at, or products dated earlier drop out of the view entirely.
SEALED_OBSERVED_AT = "2026-04-01"

# (set_code, category_keyword, market_price). The pairs mirror
# demo_data.DEMO_SEALED_PRODUCTS and are resolved with the same
# "set_code = ? AND category LIKE ? LIMIT 1" query, so the priced products are
# exactly the ones the demo sealed_collection holds.
#
# ("dsk", "bundle") is deliberately absent: leaving one demo-held product
# unpriced keeps the null-price render path ('' rather than $0.00) covered on
# the page itself.
DEMO_SEALED_PRICES = [
    ("dsk", "booster_box", 119.99),
    ("blb", "booster_box", 99.50),
    ("fdn", "booster_pack", 3.50),   # demo qty 6 -> $21.00 total
    ("mh3", "booster_pack", 11.25),  # demo qty 3 -> $33.75 total
    ("otj", "bundle", 38.75),
    ("blb", "booster_pack", 4.99),   # demo qty 4 -> $19.96 total
    ("fdn", "booster_box", 104.00),
]

# Representative market price per category, used to give the wider catalogue a
# spread of price points. Categories absent here stay unpriced.
SEALED_CATEGORY_PRICES = {
    "booster_pack": 5.25,
    "booster_box": 109.00,
    "booster_case": 640.00,
    "bundle": 42.00,
    "bundle_case": 245.00,
    "box_set": 74.50,
    "deck": 16.00,
    "limited_aid_tool": 28.00,
}

# Single-card price seeding.
#
# Every row seeded here is for a printing the demo collection does NOT hold, so
# the owned side of the fixture prices exactly as it did before this existed:
# blb/124's five-point history below is still the only price on a demo card, and
# the collection page, its totals and the price chart all read what they always
# read.  DEMO_CARDS is imported rather than restated so the two cannot drift.
#
# The unowned side is what needed it.  0 of the 7,603 printings the demo
# collection does not hold carried any price, so on `is:unowned` every row tied
# at NULL and `sort=price` returned an identical order ascending and descending
# — and `is:unowned` is the only place a >250-row page and price ordering meet,
# which left the widest paging path untestable for the column users sort by most
# (de-9tb).  A UI scenario that tried it looked broken when it was the data.
#
# Prices are derived from the printing_id, never drawn: the fixture is a
# committed 57 MB binary, and a rebuild that reshuffled every price would land as
# a multi-megabyte diff that changed nothing.
CARD_OBSERVED_AT = "2026-04-01"

# (low, high) USD, per Scryfall rarity.  Roughly the real shape of a set — the
# bands overlap, so rarity correlates with price without deciding it, and no
# sort can pass by ordering on rarity instead.
CARD_PRICE_BANDS = {
    "common": (0.02, 1.50),
    "uncommon": (0.05, 4.00),
    "rare": (0.25, 30.00),
    "mythic": (0.75, 120.00),
}

# Fraction of priced printings that also get a Card Kingdom row, and the
# fraction of those that additionally get a buylist row.
#
# The Card Kingdom retail row carries the SAME price_type as the TCGplayer one,
# which is the shape the bug lives in: latest_prices is keyed (set_code,
# collector_number, source, price_type), so a join that pins price_type and not
# source matches such a printing twice.  The grouped templates collapse it; the
# per-copy one does not.  tests/test_collection_totals.py had to synthesise this
# itself because the shared fixture could not show it.
CARD_CK_SHARE = 0.45
CARD_CK_BUYLIST_SHARE = 0.5


def _price_spread(printing_id: str, salt: str) -> float:
    """A stable 0..1 drawn from the printing's own identity."""
    digest = hashlib.sha256(f"{printing_id}:{salt}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / (1 << 64)


def seed_card_prices(conn: sqlite3.Connection) -> int:
    """Give the unowned catalogue prices.  Returns the rows written to `prices`.

    A printing is priced in the finishes it actually has — nonfoil as `normal`,
    foil or etched as `foil` — because that is what a price feed publishes.  The
    718 foil-only and etched-only printings therefore have no `normal` price, and
    since an unowned row has no copy to take a finish from it prices as `normal`,
    that leaves ~9% of `is:unowned` legitimately blank.  The NULL-price render
    and NULL-sort paths stay covered without an invented rule for skipping rows.

    Callers must refresh latest_prices afterwards.
    """
    held = {(sc, cn) for sc, cn, *_ in DEMO_CARDS}

    rows = conn.execute(
        "SELECT printing_id, set_code, collector_number, rarity, finishes "
        "FROM printings ORDER BY set_code, printing_id"
    ).fetchall()

    written = 0
    for row in rows:
        key = (row["set_code"], row["collector_number"])
        if key in held:
            continue

        finishes = set(json.loads(row["finishes"] or "[]"))
        price_types = []
        if "nonfoil" in finishes:
            price_types.append("normal")
        if finishes & {"foil", "etched"}:
            price_types.append("foil")
        if not price_types:
            continue

        pid = row["printing_id"]
        lo, hi = CARD_PRICE_BANDS.get(row["rarity"], CARD_PRICE_BANDS["common"])
        # Squared, so the draw piles up at the cheap end the way a real set does:
        # mostly chaff, with a thin tail. A flat draw would make the median of
        # every set land halfway up its band and flatten /set-value's tiers.
        base = round(lo + (hi - lo) * _price_spread(pid, "tcg") ** 2, 2)
        foil = round(base * (1.5 + 3.0 * _price_spread(pid, "foil")), 2)
        tcg = {"normal": max(base, 0.01), "foil": max(foil, 0.01)}

        # Card Kingdom disagrees with TCGplayer by a different multiplier per
        # printing, spanning 0.55x to 1.85x. A fixed ratio would leave the two
        # sources in the same rank order, and `sort=ck_price` could then pass
        # while silently sorting on the TCGplayer price.
        ck_ratio = 0.55 + 1.30 * _price_spread(pid, "ck")
        wants_ck = _price_spread(pid, "ck-pick") < CARD_CK_SHARE
        wants_buylist = wants_ck and _price_spread(pid, "bl-pick") < CARD_CK_BUYLIST_SHARE

        for price_type in price_types:
            emit = [("tcgplayer", price_type, tcg[price_type])]
            if wants_ck:
                retail = max(round(tcg[price_type] * ck_ratio, 2), 0.01)
                emit.append(("cardkingdom", price_type, retail))
                if wants_buylist:
                    emit.append(
                        ("cardkingdom", f"buylist_{price_type}", max(round(retail * 0.55, 2), 0.01))
                    )
            for source, ptype, price in emit:
                conn.execute(
                    "INSERT OR IGNORE INTO prices "
                    "(set_code, collector_number, source, price_type, price, observed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (row["set_code"], row["collector_number"], source, ptype, price,
                     CARD_OBSERVED_AT),
                )
                written += 1

    return written


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

    # Store the base-set boundaries.  Written in AllPrintings.json's own shape
    # and through the same function `mtg data import` uses, so this is the
    # ingest path with a constant standing in for the file -- and it runs
    # BEFORE the import below, so a real AllPrintings.json wins wherever it
    # disagrees.  Both writes are idempotent, so with the same numbers on each
    # side the second one changes nothing.
    sized = apply_base_set_sizes(
        conn,
        {code: {"baseSetSize": size} for code, size in FIXTURE_BASE_SET_SIZES.items()},
    )
    print(f"  Stored base_set_size for {sized} sets")

    # Import MTGJSON data if AllPrintings.json is available
    from mtg_collector.cli.data_cmd import get_allprintings_path, import_mtgjson
    if get_allprintings_path().exists():
        print("  Importing MTGJSON data (sealed products, uuid map, booster data)...")
        import_mtgjson(str(OUTPUT))
        # Trim MTGJSON tables to only the sets we need (keeps fixture small)
        conn2 = sqlite3.connect(str(OUTPUT))
        all_set_str = ",".join(f"'{s}'" for s in ALL_SETS)
        for table in ("mtgjson_printings", "mtgjson_uuid_map", "mtgjson_booster_sheets",
                       "mtgjson_booster_configs", "mtgjson_decks"):
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
    print(f"  Seeded {len(price_rows)} price rows for blb/124")

    # Give the rest of the catalogue prices — see the note on CARD_OBSERVED_AT.
    print("  Seeding single-card prices for the unowned catalogue...")
    written = seed_card_prices(conn)
    # latest_prices is materialized from prices rather than written alongside it,
    # so the two cannot disagree about which observation is the latest.
    latest = refresh_latest_prices(conn)
    print(f"    {written} price rows -> {latest} latest_prices rows")

    # Seed sealed prices. All rows share SEALED_OBSERVED_AT — see the note there.
    print("  Seeding sealed price data...")
    priced_tcg_ids: set[str] = set()

    def add_sealed_price(tcg_id: str, market: float):
        conn.execute(
            """INSERT OR IGNORE INTO sealed_prices
               (tcgplayer_product_id, low_price, mid_price, high_price,
                market_price, direct_low_price, observed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                tcg_id,
                round(market * 0.88, 2),
                round(market * 0.97, 2),
                round(market * 1.35, 2),
                market,
                round(market * 0.92, 2),
                SEALED_OBSERVED_AT,
            ),
        )
        priced_tcg_ids.add(tcg_id)

    # 1. Products the demo sealed_collection holds, resolved exactly as
    #    demo_data.load_demo_data() resolves them.
    demo_priced = 0
    for set_code, category_keyword, market in DEMO_SEALED_PRICES:
        row = conn.execute(
            "SELECT tcgplayer_product_id FROM sealed_products "
            "WHERE set_code = ? AND category LIKE ? LIMIT 1",
            (set_code, category_keyword),
        ).fetchone()
        if row is None or row["tcgplayer_product_id"] is None:
            print(f"    WARNING: no priceable product for {set_code}/{category_keyword}")
            continue
        add_sealed_price(row["tcgplayer_product_id"], market)
        demo_priced += 1
    print(f"    Priced {demo_priced} demo-held products")

    # 2. A spread across the wider catalogue. Every third product keeps a slice
    #    of the catalogue deliberately unpriced alongside the 40 that have no
    #    tcgplayer_product_id at all.
    catalogue = conn.execute(
        "SELECT tcgplayer_product_id, category FROM sealed_products "
        "WHERE tcgplayer_product_id IS NOT NULL ORDER BY tcgplayer_product_id"
    ).fetchall()
    spread_priced = 0
    for i, row in enumerate(catalogue):
        tcg_id = row["tcgplayer_product_id"]
        base = SEALED_CATEGORY_PRICES.get(row["category"])
        if base is None or tcg_id in priced_tcg_ids or i % 3 != 0:
            continue
        # Fan the price out around the category base so the data spans a range
        # rather than repeating one value per category.
        add_sealed_price(tcg_id, round(base * (0.7 + 0.05 * (i % 13)), 2))
        spread_priced += 1
    print(f"    Priced {spread_priced} further catalogue products")

    total_priced = len(priced_tcg_ids)
    unpriced = conn.execute("SELECT COUNT(*) FROM sealed_products").fetchone()[0] - total_priced
    print(f"    {total_priced} sealed products priced, {unpriced} left unpriced")

    conn.commit()

    # Compact
    print("  VACUUM...")
    conn.execute("VACUUM")
    conn.close()

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"==> Done: {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
