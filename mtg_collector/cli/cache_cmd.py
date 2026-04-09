"""Cache management commands: mtg cache all"""

import json
import sys

from mtg_collector.db import get_connection, get_shared_write_path, init_db
from mtg_collector.db.models import CardRepository, PrintingRepository, SetRepository
from mtg_collector.db.schema import rebuild_fts
from mtg_collector.services.bulk_import import resolve_reversible_oracle_id
from mtg_collector.services.scryfall import ScryfallAPI
from mtg_collector.utils import get_mtgc_home

_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"


def register(subparsers):
    """Register the cache subcommand."""
    parser = subparsers.add_parser(
        "cache",
        help="Manage local Scryfall cache",
    )
    cache_sub = parser.add_subparsers(dest="cache_command", metavar="<subcommand>")

    cache_sub.add_parser(
        "all",
        help="Download and cache all cards from Scryfall bulk data",
    )
    set_parser = cache_sub.add_parser(
        "set",
        help="Refresh a specific set from the Scryfall per-set API",
    )
    set_parser.add_argument("set_code", help="Set code to refresh (e.g. tmc)")
    parser.set_defaults(func=run)


def run(args):
    """Run the cache command."""
    if args.cache_command == "all":
        cache_all(db_path=args.db_path)
    elif args.cache_command == "set":
        cache_set(db_path=args.db_path, set_code=args.set_code)
    else:
        print("Usage: mtg cache {all,set}")
        sys.exit(1)


def cache_all(db_path: str):
    """Download Scryfall bulk data and cache all cards/sets/printings."""
    conn = get_connection(get_shared_write_path(db_path))
    init_db(conn)

    card_repo = CardRepository(conn)
    set_repo = SetRepository(conn)
    printing_repo = PrintingRepository(conn)
    api = ScryfallAPI()

    # Step 1: Fetch and upsert all sets
    print("Fetching set list from Scryfall...")
    all_sets = api.get_all_sets()
    print(f"  {len(all_sets)} sets found")

    for s in all_sets:
        set_model = api.to_set_model(s)
        set_repo.upsert(set_model)
    conn.commit()

    # Step 2: Get bulk data download URL
    print("Fetching bulk data metadata...")
    resp = api.session.get(_BULK_DATA_URL)
    resp.raise_for_status()
    bulk_meta = resp.json()

    download_uri = None
    for entry in bulk_meta.get("data", []):
        if entry.get("type") == "default_cards":
            download_uri = entry["download_uri"]
            break

    if not download_uri:
        print("Error: Could not find default_cards bulk data entry")
        sys.exit(1)

    # Step 3: Stream-download bulk JSON to temp file
    tmp_dir = get_mtgc_home()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "bulk-default-cards.json"

    print(f"Downloading bulk data to {tmp_path}...")
    with api.session.get(download_uri, stream=True) as resp:
        resp.raise_for_status()
        total = resp.headers.get("Content-Length")
        total_mb = int(total) / (1024 * 1024) if total else None

        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                mb = downloaded / (1024 * 1024)
                if total_mb:
                    print(f"\r  {mb:.0f} / {total_mb:.0f} MB", end="", flush=True)
                else:
                    print(f"\r  {mb:.0f} MB", end="", flush=True)
    print()  # newline after progress

    # Step 4: Parse and process cards
    print("Processing bulk data...")
    with open(tmp_path, "r") as f:
        cards_data = json.load(f)

    total_cards = len(cards_data)
    print(f"  {total_cards} cards in bulk data")

    processed = 0
    all_set_codes = set()

    for card_data in cards_data:
        set_code = card_data.get("set")

        # Reversible cards store oracle_id on faces, not top-level
        resolve_reversible_oracle_id(card_data)

        # Skip cards without oracle_id (tokens, etc.)
        if "oracle_id" not in card_data:
            continue

        # Skip non-English cards
        if card_data.get("lang", "en") != "en":
            continue

        card = api.to_card_model(card_data)
        card_repo.upsert(card)

        printing = api.to_printing_model(card_data)
        printing_repo.upsert(printing)

        all_set_codes.add(set_code)
        processed += 1

        # Commit every 5000 cards and print progress
        if processed % 5000 == 0:
            conn.commit()
            print(f"  Processed {processed} cards...")

    # Final commit for remaining cards
    conn.commit()

    # Step 5: Mark all processed sets as cached
    for sc in all_set_codes:
        set_repo.mark_cards_cached(sc)
    conn.commit()

    # Step 6: Backfill sets under-populated in bulk data.
    # The bulk data snapshot can lag behind the live API for pre-release,
    # newly released, or token sets. Compare local printing counts against
    # Scryfall's reported card_count and backfill via per-set API.
    expected_counts = {s["code"]: s.get("card_count", 0) for s in all_sets}
    backfill_count = 0

    cursor = conn.execute(
        "SELECT s.set_code, s.digital, COUNT(p.printing_id) as local_count"
        " FROM sets s"
        " LEFT JOIN printings p ON s.set_code = p.set_code"
        " WHERE s.digital = 0"
        " GROUP BY s.set_code"
    )
    sets_needing_backfill = []
    for row in cursor.fetchall():
        sc = row["set_code"]
        local = row["local_count"]
        expected = expected_counts.get(sc, 0)
        if expected > 0 and local < expected:
            sets_needing_backfill.append((sc, local, expected))

    if sets_needing_backfill:
        print(f"  Backfilling {len(sets_needing_backfill)} sets not fully covered by bulk data...")
        for sc, local, expected in sets_needing_backfill:
            cards = api.get_set_cards(sc)
            if not cards:
                continue
            set_backfill = 0
            for card_data in cards:
                resolve_reversible_oracle_id(card_data)
                if "oracle_id" not in card_data:
                    continue
                card = api.to_card_model(card_data)
                card_repo.upsert(card)
                printing = api.to_printing_model(card_data)
                printing_repo.upsert(printing)
                set_backfill += 1
            set_repo.mark_cards_cached(sc)
            conn.commit()
            backfill_count += set_backfill
            print(f"    {sc.upper()}: {local} → {set_backfill} cards")

    if backfill_count:
        print(f"  Backfilled {backfill_count} cards via per-set API")

    # Step 7: Non-English backfill.
    # Some physical printings only exist in non-English on Scryfall (e.g.
    # NEO Ukiyo-e Japanese basics, WAR Japanese alt-art planeswalkers).
    # After the English backfill, re-check gaps and fetch all languages
    # for sets that are still under-populated. Only insert cards for
    # collector numbers not already present locally.
    cursor = conn.execute(
        "SELECT s.set_code, COUNT(p.printing_id) as local_count"
        " FROM sets s"
        " LEFT JOIN printings p ON s.set_code = p.set_code"
        " WHERE s.digital = 0"
        " GROUP BY s.set_code"
    )
    still_gapped = []
    for row in cursor.fetchall():
        sc = row["set_code"]
        local = row["local_count"]
        expected = expected_counts.get(sc, 0)
        if expected > 0 and local < expected:
            still_gapped.append((sc, local, expected))

    non_en_count = 0
    if still_gapped:
        print(f"  Non-English backfill: {len(still_gapped)} sets still have gaps...")
        for sc, local, expected in still_gapped:
            cards = api.get_set_cards_all_langs(sc)
            if not cards:
                continue
            set_added = 0
            for card_data in cards:
                resolve_reversible_oracle_id(card_data)
                if "oracle_id" not in card_data:
                    continue
                cn = card_data["collector_number"]
                if printing_repo.get_by_set_cn(sc, cn):
                    continue  # Already have this collector number
                card = api.to_card_model(card_data)
                card_repo.upsert(card)
                printing = api.to_printing_model(card_data)
                printing_repo.upsert(printing)
                set_added += 1
            conn.commit()
            non_en_count += set_added
            if set_added:
                print(f"    {sc.upper()}: +{set_added} non-English cards ({local} → {local + set_added})")

    if non_en_count:
        print(f"  Added {non_en_count} non-English-only cards")

    # Step 8: Rebuild full-text search index
    print("Rebuilding full-text search index...")
    rebuild_fts(conn)

    # Step 9: Clean up temp file
    tmp_path.unlink(missing_ok=True)

    # Summary
    print("\nDone!")
    print(f"  Cards processed: {processed}")
    print(f"  Sets updated: {len(all_set_codes)}")


def cache_set(db_path: str, set_code: str):
    """Fetch all cards for a specific set from the Scryfall per-set API."""
    conn = get_connection(get_shared_write_path(db_path))
    init_db(conn)

    card_repo = CardRepository(conn)
    set_repo = SetRepository(conn)
    printing_repo = PrintingRepository(conn)
    api = ScryfallAPI()

    set_code = set_code.lower()

    # Ensure set metadata exists
    if not set_repo.exists(set_code):
        set_data = api.get_set(set_code)
        if not set_data:
            print(f"Set not found on Scryfall: {set_code.upper()}")
            sys.exit(1)
        set_repo.upsert(api.to_set_model(set_data))
        conn.commit()

    local_before = conn.execute(
        "SELECT COUNT(*) FROM printings WHERE set_code = ?", (set_code,)
    ).fetchone()[0]

    print(f"Fetching {set_code.upper()} from Scryfall per-set API...")
    cards = api.get_set_cards(set_code)
    if not cards:
        print(f"  No cards found for set: {set_code.upper()}")
        sys.exit(1)

    processed = 0
    for card_data in cards:
        resolve_reversible_oracle_id(card_data)
        if "oracle_id" not in card_data:
            continue
        card = api.to_card_model(card_data)
        card_repo.upsert(card)
        printing = api.to_printing_model(card_data)
        printing_repo.upsert(printing)
        processed += 1

    set_repo.mark_cards_cached(set_code)
    conn.commit()

    print(f"\nDone! {set_code.upper()}: {local_before} → {processed} cards")
