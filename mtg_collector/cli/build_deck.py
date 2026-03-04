"""Build-deck command: mtg build-deck <commander-name> [--max-calls N] [--dry-run] [--trace]"""

import sys

from mtg_collector.db import get_connection, init_db


def register(subparsers):
    p = subparsers.add_parser(
        "build-deck",
        help="Build a Commander deck from your collection using AI",
        description=(
            "Uses a Claude agent to build a 99-card Commander deck from your "
            "owned, unassigned cards. Pre-classifies cards via Scryfall otag "
            "queries, then runs an agent loop for strategy and synergy analysis."
        ),
    )
    p.add_argument("commander", help="Name of the legendary creature to use as commander")
    p.add_argument("--max-calls", type=int, default=30, help="Max agent tool calls (default: 30)")
    p.add_argument("--dry-run", action="store_true", help="Print decklist without saving to DB")
    p.add_argument("--trace", action="store_true", help="Print agent trace to stderr")
    p.set_defaults(func=run)


def run(args):
    from mtg_collector.services.deck_builder import run_deck_builder

    conn = get_connection(args.db_path)
    init_db(conn)

    trace_lines = [] if args.trace else None

    def status_cb(msg):
        if args.trace:
            print(msg, file=sys.stderr)

    try:
        result = run_deck_builder(
            commander_name=args.commander,
            conn=conn,
            max_calls=args.max_calls,
            status_callback=status_cb if args.trace else None,
            trace_out=trace_lines,
            save_deck=not args.dry_run,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Print results
    print(f"\n{'=' * 60}")
    print(f"  {result['deck_name']}")
    print(f"{'=' * 60}")
    print(f"\nStrategy: {result['strategy']}\n")

    if result.get("deck_id"):
        print(f"Deck ID: {result['deck_id']}")
    elif args.dry_run:
        print("(dry run — deck not saved)")
    print()

    # Group cards by primary category
    by_category: dict[str, list] = {}
    for card in result["cards"]:
        cat = card["categories"][0] if card["categories"] else "uncategorized"
        by_category.setdefault(cat, []).append(card)

    for category, cards in sorted(by_category.items()):
        print(f"── {category} ({len(cards)}) ──")
        for card in sorted(cards, key=lambda c: c["name"]):
            roles = ", ".join(card["categories"])
            print(f"  {card['name']:40s} [{roles}]")
        print()

    # Mana curve (from collection data)
    print(f"Total cards: {len(result['cards'])} + commander")

    # Shopping list
    if result["shopping_list"]:
        print(f"\n── Shopping List ({len(result['shopping_list'])}) ──")
        for item in result["shopping_list"]:
            print(f"  {item['name']:40s} {item['category']:20s} {item['reason']}")

    # Usage
    usage = result.get("usage", {})
    sonnet = usage.get("sonnet", {})
    if sonnet:
        print(f"\nToken usage: {sonnet.get('input', 0)} in / {sonnet.get('output', 0)} out")
