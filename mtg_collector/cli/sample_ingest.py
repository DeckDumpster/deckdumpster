"""sample-ingest command: insert sample ingest records for UI testing."""

import hashlib
import json
import shutil
from pathlib import Path

from mtg_collector.cli.crack_pack_server import _compute_card_crop
from mtg_collector.db import get_connection, init_db
from mtg_collector.db.models import CardRepository, PrintingRepository
from mtg_collector.utils import get_mtgc_home, now_iso

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"

SAMPLES = [
    {
        "name": "Mox Emerald",
        "set_code": "2ed",
        "collector_number": "262",
        "fixture": "sample-mox-emerald.jpg",
        "stored_name": "sample_mox_emerald.jpg",
        "status": "DONE",
        "confidence": "high",
        "ocr_fragments": [
            {"text": "Mox Emerald", "bbox": {"x": 143, "y": 118, "w": 285, "h": 58}, "confidence": 0.92},
            {"text": "Mono Artifact", "bbox": {"x": 223, "y": 780, "w": 250, "h": 42}, "confidence": 0.97},
            {"text": "Add 1 green mana", "bbox": {"x": 352, "y": 840, "w": 442, "h": 68}, "confidence": 0.94},
            {"text": "Illus. Dan Frazier", "bbox": {"x": 255, "y": 1134, "w": 306, "h": 45}, "confidence": 0.82},
        ],
        "image_size": [1080, 1440],
    },
    {
        "name": "Archenemy's Charm",
        "set_code": "eoe",
        "collector_number": None,  # multiple printings — leave unresolved
        "fixture": "sample-archenemys-charm.jpeg",
        "stored_name": "sample_archenemys_charm.jpg",
        "status": "READY_FOR_DISAMBIGUATION",
        "confidence": "medium",
        "ocr_fragments": [
            {"text": "Archenemy's Charm", "bbox": {"x": 187, "y": 191, "w": 360, "h": 45}, "confidence": 0.97},
            {"text": "Instant", "bbox": {"x": 184, "y": 744, "w": 118, "h": 34}, "confidence": 1.00},
            {"text": "Exile target creature or planeswalker.", "bbox": {"x": 199, "y": 841, "w": 586, "h": 51}, "confidence": 0.97},
            {"text": "EOE EN PETER DIAMOND", "bbox": {"x": 164, "y": 1163, "w": 277, "h": 36}, "confidence": 0.93},
        ],
        "image_size": [1018, 1321],
    },
    {
        "name": "Arenson's Aura",
        "set_code": "ice",
        "collector_number": None,
        "fixture": "sample-arensons-aura.jpg",
        "stored_name": "sample_arensons_aura.jpg",
        "status": "READY_FOR_DISAMBIGUATION",
        "confidence": "high",
        "artist": "Nicola Leonard",
        "extra_sets": ["ptc"],  # also has a Pro Tour Collector Set printing
        "ocr_fragments": [
            {"text": "Arenson's Aura", "bbox": {"x": 286, "y": 465, "w": 232, "h": 40}, "confidence": 0.91},
            {"text": "Enchantment", "bbox": {"x": 292, "y": 946, "w": 183, "h": 32}, "confidence": 0.99},
            {"text": "Sacrifice an enchantment to", "bbox": {"x": 329, "y": 993, "w": 407, "h": 36}, "confidence": 0.98},
            {"text": "Illus. Nicola Leonard", "bbox": {"x": 293, "y": 1246, "w": 235, "h": 29}, "confidence": 0.93},
        ],
        "image_size": [1080, 1920],
    },
    {
        "name": "Armed Response",
        "set_code": "5dn",
        "collector_number": "2",
        "fixture": "sample-armed-response.jpg",
        "stored_name": "sample_armed_response.jpg",
        "status": "DONE",
        "confidence": "high",
        "ocr_fragments": [
            {"text": "Armed Response", "bbox": {"x": 283, "y": 494, "w": 266, "h": 39}, "confidence": 0.99},
            {"text": "Instant", "bbox": {"x": 286, "y": 961, "w": 97, "h": 30}, "confidence": 1.00},
            {"text": "Armed Response deals damage to", "bbox": {"x": 293, "y": 1026, "w": 452, "h": 38}, "confidence": 0.98},
            {"text": "Doug Chaffee", "bbox": {"x": 322, "y": 1261, "w": 132, "h": 23}, "confidence": 0.96},
        ],
        "image_size": [1080, 1920],
    },
]


def register(subparsers):
    parser = subparsers.add_parser(
        "sample-ingest",
        help="Insert sample ingest data for UI testing",
    )
    parser.add_argument(
        "--nuke",
        action="store_true",
        help="Delete all ingest_images rows and their image files before inserting samples",
    )
    parser.set_defaults(func=run)


def _format_candidate(printing):
    """Format a Printing into the candidate shape the recent page expects."""
    data = printing.get_card_data()
    if not data:
        return None

    image_uri = None
    if "image_uris" in data:
        image_uri = data["image_uris"].get("small") or data["image_uris"].get("normal")
    elif "card_faces" in data and data["card_faces"]:
        face = data["card_faces"][0]
        if "image_uris" in face:
            image_uri = face["image_uris"].get("small") or face["image_uris"].get("normal")

    prices = data.get("prices", {})
    price = prices.get("usd") or prices.get("usd_foil")

    return {
        "printing_id": data["id"],
        "name": data.get("name", "???"),
        "set_code": data.get("set", "???"),
        "set_name": data.get("set_name", ""),
        "collector_number": data.get("collector_number", "???"),
        "rarity": data.get("rarity", "unknown"),
        "image_uri": image_uri,
        "foil": "foil" in data.get("finishes", []),
        "finishes": data.get("finishes", []),
        "promo": data.get("promo", False),
        "full_art": data.get("full_art", False),
        "border_color": data.get("border_color", ""),
        "frame_effects": data.get("frame_effects", []),
        "price": price,
        "artist": data.get("artist", ""),
    }


def _nuke(conn, images_dir):
    """Delete all ingest_images rows and their image files."""
    rows = conn.execute("SELECT id, stored_name FROM ingest_images").fetchall()
    for row in rows:
        filepath = images_dir / row[1]
        if filepath.is_file():
            filepath.unlink()
    conn.execute("DELETE FROM ingest_images")
    conn.commit()
    print(f"  nuked {len(rows)} ingest_images rows")


def run(args):
    conn = get_connection(args.db_path)
    init_db(conn)

    card_repo = CardRepository(conn)
    printing_repo = PrintingRepository(conn)
    images_dir = get_mtgc_home() / "ingest_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if args.nuke:
        _nuke(conn, images_dir)

    ts = now_iso()

    for sample in SAMPLES:
        # Look up card in local DB
        cards = card_repo.search_cards_by_name(sample["name"], limit=1)
        if not cards:
            print(f"  error: card '{sample['name']}' not found in local DB — run 'mtg setup' first")
            continue

        card = cards[0]
        all_printings = printing_repo.get_by_oracle_id(card.oracle_id)

        # Filter to the target set
        set_printings = [p for p in all_printings if p.set_code == sample["set_code"]]
        if not set_printings:
            print(f"  error: no printings for '{sample['name']}' in set '{sample['set_code']}' — run 'mtg setup' first")
            continue

        # Build candidates list (target set + any extra_sets)
        candidate_printings = list(set_printings)
        for extra_sc in sample.get("extra_sets", []):
            candidate_printings.extend(p for p in all_printings if p.set_code == extra_sc)

        candidates = []
        for p in candidate_printings:
            c = _format_candidate(p)
            if c:
                candidates.append(c)

        if not candidates:
            print(f"  error: no scryfall data for '{sample['name']}' in '{sample['set_code']}'")
            continue

        # Resolve the specific printing for DONE cards
        if sample["collector_number"]:
            target = printing_repo.get_by_set_cn(sample["set_code"], sample["collector_number"])
            if not target:
                print(f"  error: printing {sample['set_code']}#{sample['collector_number']} not found")
                continue
            disambiguated = [target.printing_id]
            claude_cn = sample["collector_number"]
        else:
            disambiguated = [None]
            claude_cn = None

        # Build claude_result
        ocr_result = sample["ocr_fragments"]
        all_indices = list(range(len(ocr_result)))
        claude_entry = {
            "name": sample["name"],
            "set_code": sample["set_code"],
            "confidence": sample["confidence"],
            "fragment_indices": all_indices,
        }
        if claude_cn:
            claude_entry["collector_number"] = claude_cn
        if sample.get("artist"):
            claude_entry["artist"] = sample["artist"]
        claude_result = [claude_entry]

        # Copy fixture image to ingest_images dir
        fixture_path = FIXTURES_DIR / sample["fixture"]
        image_path = images_dir / sample["stored_name"]
        shutil.copy2(str(fixture_path), str(image_path))
        md5 = hashlib.md5(image_path.read_bytes()).hexdigest()

        # Compute crop from OCR bounding boxes
        img_w, img_h = sample.get("image_size", (None, None))
        crops = [_compute_card_crop(ocr_result, all_indices, image_w=img_w, image_h=img_h)]

        # Build confirmed_finishes: for DONE cards, default to nonfoil
        if sample["status"] == "DONE" and disambiguated[0] is not None:
            confirmed_finishes = ["nonfoil"]
        else:
            confirmed_finishes = [None]

        # Insert the record
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
                json.dumps(ocr_result),
                json.dumps(claude_result),
                json.dumps([candidates]),
                json.dumps(disambiguated),
                json.dumps(confirmed_finishes),
                json.dumps(crops),
                ts,
                ts,
            ),
        )
        conn.commit()
        print(f"  inserted: {sample['stored_name']} ({sample['status']}, {len(candidates)} candidates)")

    conn.close()
    print("done")
