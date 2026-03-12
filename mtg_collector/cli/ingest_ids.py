"""Ingest-ids command: mtg ingest-ids --id R 0123 EOE [foil]"""

import sys

from mtg_collector.db import (
    CollectionRepository,
    PrintingRepository,
    SetRepository,
    get_connection,
    init_db,
)
from mtg_collector.db.models import CollectionEntry
from mtg_collector.utils import normalize_condition, normalize_finish, store_source_image

RARITY_MAP = {"C": "common", "U": "uncommon", "R": "rare", "M": "mythic", "P": "promo", "L": "common", "T": "token", "F": "rare"}


def lookup_card(set_code, cn_raw, cn_stripped, rarity_expected, printing_repo):
    """Look up a card by set/CN in the local DB, with promo/token set fallback."""
    card_data = None

    # Promo cards: try p{set_code} set with {cn}p collector number first
    if rarity_expected == "promo":
        promo_set = f"p{set_code}"
        printing = printing_repo.get_by_set_cn(promo_set, f"{cn_stripped}p")
        if not printing:
            printing = printing_repo.get_by_set_cn(promo_set, cn_stripped)
        if printing and printing.raw_json:
            card_data = printing.get_card_data()

    # Token cards: try t{set_code} set (no fallback — tokens have their own
    # collector number sequence and must not match regular cards)
    if rarity_expected == "token":
        token_set = f"t{set_code}"
        printing = printing_repo.get_by_set_cn(token_set, cn_stripped)
        if not printing:
            printing = printing_repo.get_by_set_cn(token_set, cn_raw)
        if printing and printing.raw_json:
            card_data = printing.get_card_data()
        return card_data

    # Regular lookup (also fallback for promo)
    if not card_data:
        printing = printing_repo.get_by_set_cn(set_code, cn_stripped)
        if not printing:
            printing = printing_repo.get_by_set_cn(set_code, cn_raw)
        if printing and printing.raw_json:
            card_data = printing.get_card_data()

    return card_data


def resolve_and_add_ids(
    entries,
    printing_repo,
    collection_repo,
    condition,
    source,
    source_image=None,
):
    """
    Resolve card IDs and add them to the collection.

    Args:
        entries: list of dicts, each with keys:
            rarity_code (str), rarity (str), collector_number (str),
            set_code (str, normalized), foil (bool)
        printing_repo, collection_repo: DB repositories
        condition: normalized condition string
        source: source identifier

    Returns:
        (added_count, failed_labels) tuple
    """
    failed = []
    added = 0

    for entry in entries:
        set_code = entry["set_code"]
        cn_raw = entry["collector_number"]
        cn_stripped = cn_raw.lstrip("0") or "0"
        rarity_expected = entry["rarity"]
        is_foil = entry.get("foil", False)

        label = f"{entry['rarity_code']} {cn_raw} {set_code.upper()}"
        if is_foil:
            label += " foil"

        card_data = lookup_card(
            set_code, cn_raw, cn_stripped, rarity_expected,
            printing_repo,
        )

        if not card_data:
            if rarity_expected == "token":
                token_set = f"t{set_code}"
                print(f"  FAILED: {label} — token not found in {token_set} (run `mtg cache all` to refresh token data)")
            else:
                print(f"  FAILED: {label} — card not found (run `mtg cache all` to populate)")
            failed.append(label)
            continue

        # Warn on rarity mismatch (promos use a separate boolean, not a rarity string;
        # tokens are labeled "common" which is expected)
        actual_rarity = card_data.get("rarity", "")
        if rarity_expected == "promo":
            if not card_data.get("promo", False):
                print(
                    f"  Warning: {label} — expected promo, "
                    f"DB reports non-promo '{actual_rarity}'"
                )
        elif rarity_expected == "token":
            pass  # Tokens are labeled "common", no mismatch to warn about
        elif actual_rarity != rarity_expected:
            print(
                f"  Warning: {label} — expected rarity '{rarity_expected}', "
                f"DB reports '{actual_rarity}'"
            )

        # Create collection entry
        finish = normalize_finish("foil" if is_foil else "nonfoil")
        collection_entry = CollectionEntry(
            id=None,
            printing_id=card_data["id"],
            finish=finish,
            condition=condition,
            source=source,
            source_image=source_image,
        )
        entry_id = collection_repo.add(collection_entry)
        card_name = card_data.get("name", "Unknown")
        cn_display = card_data.get("collector_number", cn_raw)
        print(
            f"  Added (ID: {entry_id}): {card_name} "
            f"({set_code.upper()} #{cn_display}) [{finish}]"
        )
        added += 1

    return added, failed


def register(subparsers):
    """Register the ingest-ids subcommand."""
    parser = subparsers.add_parser(
        "ingest-ids",
        help="Add cards by rarity, collector number, and set code",
        description=(
            "Add cards to your collection using rarity/collector-number/set triples. "
            "Example: mtg ingest-ids --id R 0123 EOE --id C 0187 EOE foil"
        ),
    )
    parser.add_argument(
        "--id",
        nargs="+",
        action="append",
        required=True,
        metavar="FIELD",
        help="RARITY CN SET [foil] — e.g. R 0123 EOE or C 0187 EOE foil",
    )
    parser.add_argument(
        "--source",
        default="manual_id",
        help="Source identifier for these cards (default: manual_id)",
    )
    parser.add_argument(
        "--condition",
        default="Near Mint",
        help="Condition for all cards (default: Near Mint)",
    )
    parser.add_argument(
        "--source-image",
        default=None,
        help="File path of the source image these cards came from",
    )
    parser.set_defaults(func=run)


def run(args):
    """Run the ingest-ids command."""
    # Parse and validate all --id arguments up front
    parsed_ids = []
    for id_fields in args.id:
        if len(id_fields) < 3 or len(id_fields) > 4:
            print(
                f"Error: --id requires 3 or 4 values (RARITY CN SET [foil]), got {len(id_fields)}: {id_fields}"
            )
            sys.exit(1)

        rarity_code = id_fields[0].upper()
        collector_number = id_fields[1]
        set_code_raw = id_fields[2]
        is_foil = len(id_fields) == 4 and id_fields[3].lower() == "foil"

        if rarity_code not in RARITY_MAP:
            print(
                f"Error: Invalid rarity '{rarity_code}'. Use C (common), U (uncommon), R (rare), M (mythic), P (promo)."
            )
            sys.exit(1)

        parsed_ids.append({
            "rarity_code": rarity_code,
            "rarity": RARITY_MAP[rarity_code],
            "collector_number": collector_number,
            "set_code_raw": set_code_raw,
            "is_foil": is_foil,
        })

    # Initialize database
    conn = get_connection(args.db_path)
    init_db(conn)

    set_repo = SetRepository(conn)
    printing_repo = PrintingRepository(conn)
    collection_repo = CollectionRepository(conn)

    # Normalize and validate set codes
    unique_sets = {}
    for entry in parsed_ids:
        raw = entry["set_code_raw"]
        if raw.lower() not in unique_sets:
            normalized = set_repo.normalize_code(raw)
            if not normalized:
                print(f"Error: Unknown set code '{raw}' (run `mtg cache all` to populate)")
                sys.exit(1)
            unique_sets[raw.lower()] = normalized
        entry["set_code"] = unique_sets[raw.lower()]
        entry["foil"] = entry.pop("is_foil")

    condition = normalize_condition(args.condition)

    added, failed = resolve_and_add_ids(
        entries=parsed_ids,
        printing_repo=printing_repo,
        collection_repo=collection_repo,
        condition=condition,
        source=args.source,
        source_image=store_source_image(args.source_image) if args.source_image else None,
    )

    # Commit or rollback
    if failed:
        conn.rollback()
        print()
        print(f"FAILED — {len(failed)} card(s) could not be resolved:")
        for f in failed:
            print(f"  - {f}")
        print("No cards were added. Fix the issues above and try again.")
        sys.exit(1)
    else:
        conn.commit()
        print()
        print(f"Done! Added {added} card(s) to collection.")
