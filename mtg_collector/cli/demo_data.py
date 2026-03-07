"""Demo fixture data for new installations.

Provides ~45 curated cards across various sets, statuses, conditions, and finishes
so the web UI has realistic data to browse immediately after setup.

Card names in comments are resolved from the local Scryfall DB at runtime.
The names listed here match test-data.sqlite (built by scripts/build_test_fixture.py).
To verify: query `printings JOIN cards` by (set_code, collector_number).

Index layout:
  0-7:   Bolt Tribal deck (FDN cards)
  8-13:  Trade Binder (DSK cards)
  14-19: Foil Collection binder (BLB + OTJ cards)
  20-25: Eldrazi Ramp deck (OTJ + MH3 cards)
  26-32: Unassigned owned (SPG, WOE, LCI, MKM)
  33-34: Duplicate copies (unassigned owned)
  35-39: TCG order (owned, linked to DEMO-TCG-001)
  40-44: CK order (ordered, linked to DEMO-CK-001)
"""

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from mtg_collector.db.models import (
    Binder,
    BinderRepository,
    CollectionEntry,
    CollectionRepository,
    CollectionView,
    CollectionViewRepository,
    CornerBatch,
    CornerBatchRepository,
    Deck,
    DeckRepository,
    Order,
    OrderRepository,
    SealedCollectionEntry,
    SealedCollectionRepository,
    WishlistEntry,
    WishlistRepository,
)
from mtg_collector.utils import get_mtgc_home, now_iso

# Each tuple: (set_code, collector_number, finish, condition, status)
# status is one of: "owned", "ordered"
# Cards tagged "ordered" will be linked to a demo order.
DEMO_CARDS = [
    # --- Foundations (FDN) — commons/uncommons/rares ---
    ("fdn", "132", "nonfoil", "Near Mint", "owned"),         # 0: Scrawling Crawler
    ("fdn", "132", "foil", "Near Mint", "owned"),             # 1: Scrawling Crawler (foil dupe)
    ("fdn", "100", "nonfoil", "Near Mint", "owned"),          # 2: Beast-Kin Ranger
    ("fdn", "60", "nonfoil", "Near Mint", "owned"),           # 3: Gutless Plunderer
    ("fdn", "34", "nonfoil", "Near Mint", "owned"),           # 4: Curator of Destinies
    ("fdn", "90", "nonfoil", "Near Mint", "owned"),           # 5: Incinerating Blast
    ("fdn", "191", "nonfoil", "Near Mint", "owned"),          # 6: Brazen Scourge
    ("fdn", "103", "nonfoil", "Lightly Played", "owned"),     # 7: Elfsworn Giant

    # --- Duskmourn (DSK) — horror set variety ---
    ("dsk", "1", "nonfoil", "Near Mint", "owned"),            # 8: Acrobatic Cheerleader
    ("dsk", "119", "nonfoil", "Near Mint", "owned"),          # 9: Unstoppable Slasher
    ("dsk", "197", "foil", "Near Mint", "owned"),             # 10: Say Its Name
    ("dsk", "216", "nonfoil", "Moderately Played", "owned"),  # 11: Growing Dread
    ("dsk", "107", "nonfoil", "Near Mint", "owned"),          # 12: Live or Die
    ("dsk", "224", "nonfoil", "Near Mint", "owned"),          # 13: Niko, Light of Hope

    # --- Bloomburrow (BLB) — cute animal set ---
    ("blb", "198", "nonfoil", "Near Mint", "owned"),          # 14: Three Tree Rootweaver
    ("blb", "124", "nonfoil", "Near Mint", "owned"),          # 15: Artist's Talent
    ("blb", "156", "nonfoil", "Near Mint", "owned"),          # 16: Take Out the Trash
    ("blb", "215", "foil", "Near Mint", "owned"),             # 17: Glarb, Calamity's Augur

    # --- Outlaws of Thunder Junction (OTJ) ---
    ("otj", "178", "nonfoil", "Near Mint", "owned"),          # 18: Reach for the Sky
    ("otj", "90", "nonfoil", "Near Mint", "owned"),           # 19: Hollow Marauder
    ("otj", "196", "nonfoil", "Near Mint", "owned"),          # 20: Bonny Pall, Clearcutter
    ("otj", "233", "foil", "Near Mint", "owned"),             # 21: Slick Sequence

    # --- Modern Horizons 3 (MH3) ---
    ("mh3", "209", "nonfoil", "Near Mint", "owned"),          # 22: Disruptor Flute
    ("mh3", "293", "nonfoil", "Near Mint", "owned"),          # 23: Junk Diver
    ("mh3", "197", "nonfoil", "Lightly Played", "owned"),     # 24: Phlage, Titan of Fire's Fury
    ("mh3", "196", "etched", "Near Mint", "owned"),           # 25: Ondu Knotmaster // Throw a Line

    # --- Special Guests (SPG) — borderless promos ---
    ("spg", "74", "nonfoil", "Near Mint", "owned"),           # 26: Condemn

    # --- Wilds of Eldraine (WOE) ---
    ("woe", "56", "nonfoil", "Near Mint", "owned"),           # 27: Ingenious Prodigy
    ("woe", "171", "nonfoil", "Near Mint", "owned"),          # 28: Graceful Takedown

    # --- The Lost Caverns of Ixalan (LCI) ---
    ("lci", "68", "nonfoil", "Near Mint", "owned"),           # 29: Orazca Puzzle-Door
    ("lci", "113", "nonfoil", "Lightly Played", "owned"),     # 30: Preacher of the Schism

    # --- Murders at Karlov Manor (MKM) ---
    ("mkm", "172", "nonfoil", "Near Mint", "owned"),          # 31: The Pride of Hull Clade
    ("mkm", "210", "foil", "Near Mint", "owned"),             # 32: Judith, Carnage Connoisseur

    # --- Duplicate cards (same printing, different copies) ---
    ("fdn", "132", "nonfoil", "Near Mint", "owned"),          # 33: Scrawling Crawler #3
    ("dsk", "119", "nonfoil", "Near Mint", "owned"),          # 34: Unstoppable Slasher #2

    # === ORDERED cards (linked to demo orders) ===
    # Order 1: TCGPlayer order (received — these become "owned")
    ("fdn", "63", "nonfoil", "Near Mint", "owned"),           # 35: Infernal Vessel
    ("fdn", "166", "nonfoil", "Near Mint", "owned"),          # 36: Time Stop
    ("fdn", "94", "foil", "Near Mint", "owned"),              # 37: Slumbering Cerberus
    ("fdn", "139", "nonfoil", "Near Mint", "owned"),          # 38: Cathar Commando
    ("fdn", "168", "nonfoil", "Near Mint", "owned"),          # 39: Witness Protection

    # Order 2: Card Kingdom order (pending — status=ordered)
    ("mh3", "174", "nonfoil", "Near Mint", "ordered"),        # 40: Thief of Existence
    ("mh3", "295", "nonfoil", "Near Mint", "ordered"),        # 41: Ruby Medallion
    ("mh3", "234", "nonfoil", "Near Mint", "ordered"),        # 42: Urza's Cave
    ("blb", "188", "foil", "Near Mint", "ordered"),           # 43: Peerless Recycling
    ("dsk", "173", "nonfoil", "Near Mint", "ordered"),        # 44: Coordinated Clobbering
]

# Demo orders
DEMO_ORDERS = [
    {
        "order_number": "DEMO-TCG-001",
        "source": "tcgplayer",
        "seller_name": "CardHaus Gaming",
        "order_date": "2025-01-15",
        "subtotal": 24.97,
        "shipping": 2.99,
        "tax": 2.12,
        "total": 30.08,
        "shipping_status": "Delivered",
        "cards_slice": slice(35, 40),  # indices into DEMO_CARDS
    },
    {
        "order_number": "DEMO-CK-001",
        "source": "cardkingdom",
        "seller_name": "Card Kingdom",
        "order_date": "2025-02-01",
        "subtotal": 42.50,
        "shipping": 0.00,
        "tax": 4.25,
        "total": 46.75,
        "shipping_status": "Shipped",
        "cards_slice": slice(40, 45),  # indices into DEMO_CARDS
    },
]

# Demo wishlist entries: (set_code, collector_number, notes, priority, max_price)
DEMO_WISHLIST = [
    ("mh3", "209", "Need for Commander deck", 2, 50.00),      # Disruptor Flute
    ("dsk", "224", None, 1, None),                              # Niko, Light of Hope
    ("otj", "196", "For combo deck", 3, 25.00),                # Bonny Pall, Clearcutter
]

# Each tuple: (set_code, category_keyword, quantity, purchase_price, status)
# Looked up from sealed_products by set_code + category LIKE match.
DEMO_SEALED_PRODUCTS = [
    # Booster boxes
    ("dsk", "booster_box", 1, 105.00, "owned"),          # Duskmourn booster box
    ("blb", "booster_box", 1, 110.00, "owned"),           # Bloomburrow booster box

    # Booster packs
    ("fdn", "booster_pack", 6, 4.50, "owned"),            # Foundations packs
    ("mh3", "booster_pack", 3, 9.00, "owned"),            # MH3 packs

    # Bundles
    ("otj", "bundle", 1, 45.00, "owned"),                 # Thunder Junction bundle
    ("dsk", "bundle", 1, 40.00, "owned"),                  # Duskmourn bundle

    # Status variety
    ("blb", "booster_pack", 4, 4.25, "opened"),           # Opened BLB packs
    ("fdn", "booster_box", 1, 130.00, "listed"),          # Listed FDN box
]

# Demo decks — assigned from owned cards by DEMO_CARDS index
DEMO_DECKS = [
    {
        "name": "Bolt Tribal",
        "format": "modern",
        "description": "Burn deck",
        "cards_slice": slice(0, 8),      # First 8 FDN cards (owned)
        "zone": "mainboard",
    },
    {
        "name": "Eldrazi Ramp",
        "format": "commander",
        "description": "Big mana Eldrazi",
        "sleeve_color": "black",
        "deck_box": "Ultimate Guard Boulder 100+",
        "cards_slice": slice(20, 26),    # MH3 + SPG cards (owned)
        "zone": "mainboard",
    },
]

# Demo binders — assigned from owned cards by DEMO_CARDS index
DEMO_BINDERS = [
    {
        "name": "Trade Binder",
        "color": "blue",
        "binder_type": "9-pocket",
        "cards_slice": slice(8, 14),     # DSK cards (owned)
    },
    {
        "name": "Foil Collection",
        "color": "black",
        "description": "Premium cards",
        "cards_slice": slice(14, 20),    # BLB + OTJ cards (owned)
    },
]

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"

# Demo ingest samples — cards identified by the agent, shown on the Recents page.
# OCR/claude data captured from real ingest sessions.
DEMO_INGEST_SAMPLES = [
    {
        "name": "Aetherflame Wall",
        "target_set": "tsp",
        "target_cn": "142",
        "candidate_sets": ["tsp"],
        "fixture": "sample-aetherflame-wall.jpg",
        "stored_name": "sample_aetherflame_wall.jpg",
        "status": "DONE",
        "ocr_fragments": [
            {"text": "Atherflame Wall", "bbox": {"x": 208.0, "y": 498.0, "w": 258.0, "h": 35.0}, "confidence": 0.986},
            {"text": "Creature-Wall", "bbox": {"x": 207.0, "y": 950.0, "w": 217.0, "h": 31.0}, "confidence": 0.984},
            {"text": "Defender", "bbox": {"x": 210.0, "y": 1020.0, "w": 132.0, "h": 30.0}, "confidence": 0.997},
            {"text": "with shadow as though they didn't have shadow. AEtherflame Wall can block creatures", "bbox": {"x": 209.0, "y": 1059.0, "w": 497.0, "h": 91.0}, "confidence": 0.97},
            {"text": "end of turn. :AEtherflame Wall gets +1/+0 until", "bbox": {"x": 207.0, "y": 1160.0, "w": 500.0, "h": 64.0}, "confidence": 0.932},
            {"text": "0/4", "bbox": {"x": 658.0, "y": 1244.0, "w": 66.0, "h": 37.0}, "confidence": 0.995},
            {"text": "Justin Sweet", "bbox": {"x": 244.0, "y": 1262.0, "w": 123.0, "h": 23.0}, "confidence": 0.98},
            {"text": "1993-2006.Wiznrds-ofthe-Coast", "bbox": {"x": 230.0, "y": 1288.0, "w": 228.0, "h": 17.0}, "confidence": 0.802},
        ],
        "claude_result": [
            {"name": "Aetherflame Wall", "printing_ids": ["93b14f08-dd93-4a9f-a616-8f8d0b26b966"], "fragment_indices": [0, 1, 2, 3, 4, 5, 6, 7]},
        ],
        "crops": [{"x": 119, "y": 417, "w": 693, "h": 968}],
    },
    {
        # Just-uploaded image — server processes on startup via fake agent.
        # Unicode artist bug in _resolve_candidates causes empty scryfall_matches.
        "fixture": "sample-brimstone-mage.jpg",
        "stored_name": "sample_brimstone_mage.jpg",
        "status": "READY_FOR_OCR",
    },
    {
        # Michiko's Reign of Truth — double-faced saga from NEO.
        "fixture": "sample-michikos-reign-of-truth.jpg",
        "stored_name": "sample_michikos_reign_of_truth.jpg",
        "status": "READY_FOR_OCR",
    },
    {
        "name": "Canyon Wildcat",
        "target_set": "ddh",
        "target_cn": "6",
        "candidate_sets": ["ddh", "tmp", "8ed"],
        "fixture": "sample-canyon-wildcat.jpg",
        "stored_name": "sample_canyon_wildcat.jpg",
        "status": "DONE",
        "ocr_fragments": [
            {"text": "Canyon Wildcat", "bbox": {"x": 216.0, "y": 510.0, "w": 240.0, "h": 33.0}, "confidence": 0.981},
            {"text": "8", "bbox": {"x": 684.0, "y": 947.0, "w": 28.0, "h": 26.0}, "confidence": 0.915},
            {"text": "Creature-Cat", "bbox": {"x": 213.0, "y": 948.0, "w": 195.0, "h": 27.0}, "confidence": 0.985},
            {"text": "unblockable as long as defending player Mountainwalk (This creature is controls a Mountain.)", "bbox": {"x": 217.0, "y": 1010.0, "w": 505.0, "h": 93.0}, "confidence": 0.974},
            {"text": "tracking sense and ability to climb walls. used in the hunt are prized for their In the warrior kingdom of Keld, the cats", "bbox": {"x": 215.0, "y": 1121.0, "w": 505.0, "h": 99.0}, "confidence": 0.97},
            {"text": "2/1", "bbox": {"x": 653.0, "y": 1230.0, "w": 54.0, "h": 35.0}, "confidence": 0.995},
        ],
        "claude_result": [
            {"name": "Canyon Wildcat", "printing_ids": ["ef69547a-c060-45ac-9478-10fbe324cd42", "0169e52b-7909-4a8f-8ca2-62f030f9a85a", "7a761bfc-71dc-40be-8184-6e0be2f25d07", "f6acfd70-b866-44c8-862d-f66e28fb61bf"], "fragment_indices": [0, 2, 3, 4, 5]},
        ],
        "crops": [{"x": 143, "y": 434, "w": 649, "h": 906}],
    },
    # --- Additional test card photos (READY_FOR_OCR — processed by agent on startup) ---
    {"fixture": "camera_2026-03-05T04-45-53_184.jpg", "stored_name": "camera_2026_03_05_04_45_53_184.jpg", "status": "READY_FOR_OCR"},  # TMT Swamp
    {"fixture": "camera_2026-03-05T17-20-15_11.jpg", "stored_name": "camera_2026_03_05_17_20_15_11.jpg", "status": "READY_FOR_OCR"},  # Era of Enlightenment
    {"fixture": "signal-2026-03-05-101048.jpeg", "stored_name": "signal_2026_03_05_101048.jpeg", "status": "READY_FOR_OCR"},  # Zen Plains
]

# Demo corner batches — uses unassigned owned cards by DEMO_CARDS index
# Batch 1: assigned to "Bolt Tribal" deck (cards 26-28)
# Batch 2: unassigned (cards 29-32), for retroactive assignment test
DEMO_CORNER_BATCHES = [
    {
        "batch_uuid": "demo-batch-001",
        "name": "Wednesday evening scan",
        "assign_to_deck": "Bolt Tribal",
        "deck_zone": "sideboard",
        "cards_slice": slice(26, 29),  # SPG + WOE cards
    },
    {
        "batch_uuid": "demo-batch-002",
        "name": "New cards from LGS",
        "cards_slice": slice(29, 33),  # LCI + MKM cards
    },
]

# Demo saved views
DEMO_VIEWS = [
    {"name": "Unassigned Cards", "filters_json": '{"container":"unassigned","q":""}'},
    {"name": "Modern Staples", "filters_json": '{"container":"","q":"crawler"}'},
]


def _build_ingest_candidate(row):
    """Build an ingest candidate dict from a printings DB row."""
    finishes = json.loads(row["finishes"]) if row["finishes"] else ["nonfoil"]
    frame_effects = json.loads(row["frame_effects"]) if row["frame_effects"] else []
    price = None
    if row["raw_json"]:
        prices = json.loads(row["raw_json"]).get("prices", {})
        price = prices.get("usd") or prices.get("usd_foil")
    return {
        "printing_id": row["printing_id"],
        "name": row["name"],
        "set_code": row["set_code"],
        "set_name": row["set_name"],
        "collector_number": row["collector_number"],
        "rarity": row["rarity"],
        "image_uri": row["image_uri"],
        "foil": "foil" in finishes,
        "finishes": finishes,
        "promo": bool(row["promo"]),
        "full_art": bool(row["full_art"]),
        "border_color": row["border_color"] or "",
        "frame_effects": frame_effects,
        "price": price,
        "artist": row["artist"] or "",
    }


def _load_demo_ingest(conn, ts):
    """Load demo ingest samples for the recents page.

    Returns the number of ingest records added.
    """
    if not FIXTURES_DIR.is_dir():
        return 0

    images_dir = get_mtgc_home() / "ingest_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    added = 0

    for sample in DEMO_INGEST_SAMPLES:
        fixture_path = FIXTURES_DIR / sample["fixture"]
        if not fixture_path.is_file():
            continue

        # Copy fixture image
        image_path = images_dir / sample["stored_name"]
        shutil.copy2(str(fixture_path), str(image_path))
        md5 = hashlib.md5(image_path.read_bytes()).hexdigest()

        # Unprocessed: insert as just-uploaded, then run the processing
        # pipeline immediately.
        if sample["status"] == "READY_FOR_OCR":
            from mtg_collector.cli.crack_pack_server import _process_image_background

            cursor = conn.execute(
                """INSERT INTO ingest_images
                   (filename, stored_name, md5, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sample["stored_name"], sample["stored_name"], md5,
                 "READY_FOR_OCR", ts, ts),
            )
            image_id = cursor.lastrowid
            conn.commit()

            db_path = conn.execute("PRAGMA database_list").fetchone()[2]
            _process_image_background(db_path, image_id)

            added += 1
            continue

        # Look up card
        card_row = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = ?",
            (sample["name"],),
        ).fetchone()
        if not card_row:
            continue

        # Build candidates from specified sets
        candidates = []
        for sc in sample["candidate_sets"]:
            rows = conn.execute(
                """SELECT p.printing_id, c.name, p.set_code, s.set_name,
                          p.collector_number, p.rarity, p.image_uri,
                          p.finishes, p.promo, p.full_art, p.border_color,
                          p.frame_effects, p.artist, p.raw_json
                   FROM printings p
                   JOIN cards c ON p.oracle_id = c.oracle_id
                   JOIN sets s ON p.set_code = s.set_code
                   WHERE p.oracle_id = ? AND p.set_code = ?""",
                (card_row["oracle_id"], sc),
            ).fetchall()
            for row in rows:
                candidates.append(_build_ingest_candidate(row))

        if not candidates:
            continue

        # Resolve target printing
        target = conn.execute(
            "SELECT printing_id FROM printings WHERE set_code = ? AND collector_number = ?",
            (sample["target_set"], sample["target_cn"]),
        ).fetchone()
        if not target:
            continue

        conn.execute(
            """INSERT INTO ingest_images
               (filename, stored_name, md5, status, ocr_result, claude_result,
                scryfall_matches, disambiguated, confirmed_finishes, crops,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sample["stored_name"],
                sample["stored_name"],
                md5,
                sample["status"],
                json.dumps(sample["ocr_fragments"]),
                json.dumps(sample["claude_result"]),
                json.dumps([candidates]),
                json.dumps([target["printing_id"]]),
                json.dumps(["nonfoil"]),
                json.dumps(sample["crops"]),
                ts,
                ts,
            ),
        )
        added += 1

    return added


def wipe_user_data(conn: sqlite3.Connection):
    """Delete all user data tables, preserving card/set/printing cache."""
    # Order matters: FK constraints require children first
    conn.execute("DELETE FROM ingest_lineage")
    conn.execute("DELETE FROM status_log")
    conn.execute("DELETE FROM collection")
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM wishlist")
    conn.execute("DELETE FROM decks")
    conn.execute("DELETE FROM binders")
    conn.execute("DELETE FROM collection_views")
    conn.execute("DELETE FROM sealed_collection")
    conn.execute("DELETE FROM ingest_images")
    conn.execute("DELETE FROM ingest_cache")
    conn.execute("DELETE FROM settings WHERE key = 'demo_loaded'")
    conn.commit()


def load_demo_data(conn: sqlite3.Connection) -> bool:
    """Load demo fixture data into the database.

    Returns True if data was loaded, False if already present.
    """
    # Idempotency check
    cursor = conn.execute(
        "SELECT value FROM settings WHERE key = 'demo_loaded'"
    )
    row = cursor.fetchone()
    if row is not None:
        return False

    collection_repo = CollectionRepository(conn)
    order_repo = OrderRepository(conn)
    wishlist_repo = WishlistRepository(conn)

    ts = now_iso()

    # Build printing_id lookup for all demo cards
    resolved = []
    missing = []
    for i, (set_code, cn, finish, condition, status) in enumerate(DEMO_CARDS):
        cursor = conn.execute(
            "SELECT printing_id FROM printings WHERE set_code = ? AND collector_number = ?",
            (set_code, cn),
        )
        row = cursor.fetchone()
        if row:
            resolved.append((i, row["printing_id"], finish, condition, status))
        else:
            missing.append(f"  {set_code.upper()} #{cn}")

    if missing:
        print(f"  WARNING: {len(missing)} card(s) not in Scryfall cache (run 'mtg cache all' first):")
        for m in missing[:5]:
            print(m)
        if len(missing) > 5:
            print(f"  ... and {len(missing) - 5} more")
        if not resolved:
            print("  No cards could be resolved. Aborting demo data load.")
            return False

    # Create demo orders first (need order IDs for collection entries)
    order_ids = []
    for order_def in DEMO_ORDERS:
        order = Order(
            id=None,
            order_number=order_def["order_number"],
            source=order_def["source"],
            seller_name=order_def["seller_name"],
            order_date=order_def["order_date"],
            subtotal=order_def["subtotal"],
            shipping=order_def["shipping"],
            tax=order_def["tax"],
            total=order_def["total"],
            shipping_status=order_def["shipping_status"],
            created_at=ts,
        )
        oid = order_repo.add(order)
        order_ids.append(oid)

    # Build order index: card index → (order_db_id, order_def_index)
    order_card_map = {}
    for oi, order_def in enumerate(DEMO_ORDERS):
        s = order_def["cards_slice"]
        for ci in range(s.start, s.stop):
            order_card_map[ci] = order_ids[oi]

    # Create collection entries, tracking IDs by original DEMO_CARDS index
    added = 0
    collection_id_by_card_idx = {}
    for card_idx, printing_id, finish, condition, status in resolved:
        order_id = order_card_map.get(card_idx)
        source = "order_import" if order_id else "demo"

        entry = CollectionEntry(
            id=None,
            printing_id=printing_id,
            finish=finish,
            condition=condition,
            status=status,
            source=source,
            acquired_at=ts,
            order_id=order_id,
        )
        entry_id = collection_repo.add(entry)
        collection_id_by_card_idx[card_idx] = entry_id
        added += 1

    # Create sealed collection entries
    sealed_repo = SealedCollectionRepository(conn)
    sealed_added = 0
    for set_code, category_keyword, quantity, purchase_price, status in DEMO_SEALED_PRODUCTS:
        cursor = conn.execute(
            "SELECT uuid FROM sealed_products WHERE set_code = ? AND category LIKE ? LIMIT 1",
            (set_code, f"%{category_keyword}%"),
        )
        row = cursor.fetchone()
        if not row:
            continue
        entry = SealedCollectionEntry(
            id=None,
            sealed_product_uuid=row["uuid"],
            quantity=quantity,
            purchase_price=purchase_price,
            status=status,
            source="demo",
            added_at=ts,
        )
        sealed_repo.add(entry)
        sealed_added += 1

    # Create wishlist entries
    wishlist_added = 0
    for set_code, cn, notes, priority, max_price in DEMO_WISHLIST:
        cursor = conn.execute(
            "SELECT oracle_id, printing_id FROM printings WHERE set_code = ? AND collector_number = ?",
            (set_code, cn),
        )
        row = cursor.fetchone()
        if not row:
            continue

        entry = WishlistEntry(
            id=None,
            oracle_id=row["oracle_id"],
            printing_id=row["printing_id"],
            max_price=max_price,
            priority=priority,
            notes=notes,
            added_at=ts,
            source="demo",
        )
        wishlist_repo.add(entry)
        wishlist_added += 1

    # Create demo decks and assign cards
    deck_repo = DeckRepository(conn)
    decks_created = 0
    for deck_def in DEMO_DECKS:
        deck = Deck(
            id=None,
            name=deck_def["name"],
            description=deck_def.get("description"),
            format=deck_def.get("format"),
            sleeve_color=deck_def.get("sleeve_color"),
            deck_box=deck_def.get("deck_box"),
        )
        deck_id = deck_repo.add(deck)
        # Collect owned collection IDs within the cards_slice
        s = deck_def["cards_slice"]
        card_ids = [
            collection_id_by_card_idx[ci]
            for ci in range(s.start, s.stop)
            if ci in collection_id_by_card_idx
            and DEMO_CARDS[ci][4] == "owned"
        ]
        if card_ids:
            deck_repo.add_cards(deck_id, card_ids, zone=deck_def.get("zone", "mainboard"))
        decks_created += 1

    # Create demo binders and assign cards
    binder_repo = BinderRepository(conn)
    binders_created = 0
    for binder_def in DEMO_BINDERS:
        binder = Binder(
            id=None,
            name=binder_def["name"],
            description=binder_def.get("description"),
            color=binder_def.get("color"),
            binder_type=binder_def.get("binder_type"),
        )
        binder_id = binder_repo.add(binder)
        s = binder_def["cards_slice"]
        card_ids = [
            collection_id_by_card_idx[ci]
            for ci in range(s.start, s.stop)
            if ci in collection_id_by_card_idx
            and DEMO_CARDS[ci][4] == "owned"
        ]
        if card_ids:
            binder_repo.add_cards(binder_id, card_ids)
        binders_created += 1

    # Create demo corner batches
    batch_repo = CornerBatchRepository(conn)
    batches_created = 0
    for batch_def in DEMO_CORNER_BATCHES:
        # Find deck ID if batch should be assigned
        assign_deck_id = None
        if "assign_to_deck" in batch_def:
            row = conn.execute(
                "SELECT id FROM decks WHERE name = ?", (batch_def["assign_to_deck"],)
            ).fetchone()
            if row:
                assign_deck_id = row["id"]

        batch = CornerBatch(
            id=None,
            batch_uuid=batch_def["batch_uuid"],
            name=batch_def.get("name"),
            deck_id=assign_deck_id,
            deck_zone=batch_def.get("deck_zone") if assign_deck_id else None,
        )
        batch_id = batch_repo.create(batch)

        s = batch_def["cards_slice"]
        batch_card_ids = []
        for ci in range(s.start, s.stop):
            if ci in collection_id_by_card_idx:
                cid = collection_id_by_card_idx[ci]
                batch_card_ids.append(cid)
                # Create lineage record linking to batch
                conn.execute(
                    """INSERT INTO ingest_lineage
                       (collection_id, image_md5, image_path, card_index, batch_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cid, "demo", "demo.jpg", ci - s.start, batch_id, ts),
                )

        if batch_card_ids:
            batch_repo.increment_card_count(batch_id, len(batch_card_ids))

        # Assign cards to deck if specified
        if assign_deck_id and batch_card_ids:
            deck_repo.add_cards(assign_deck_id, batch_card_ids,
                                zone=batch_def.get("deck_zone", "mainboard"))

        batches_created += 1

    # Create demo saved views
    view_repo = CollectionViewRepository(conn)
    views_created = 0
    for view_def in DEMO_VIEWS:
        view = CollectionView(
            id=None,
            name=view_def["name"],
            filters_json=view_def.get("filters_json"),
        )
        view_repo.add(view)
        views_created += 1

    # Create demo ingest samples (recents page)
    ingest_added = _load_demo_ingest(conn, ts)

    # Mark demo as loaded
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('demo_loaded', ?)",
        (ts,),
    )

    conn.commit()

    print(f"  Added {added} collection entries ({len(missing)} skipped — not cached)")
    print(f"  Created {len(order_ids)} demo orders")
    print(f"  Added {sealed_added} sealed collection entries")
    print(f"  Added {wishlist_added} wishlist entries")
    print(f"  Created {decks_created} demo decks")
    print(f"  Created {binders_created} demo binders")
    print(f"  Created {batches_created} demo corner batches")
    print(f"  Created {views_created} demo views")
    print(f"  Added {ingest_added} demo ingest samples")

    return True
