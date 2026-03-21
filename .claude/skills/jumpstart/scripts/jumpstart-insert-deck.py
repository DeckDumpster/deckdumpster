#!/usr/bin/env python3
"""Insert a finished Jumpstart pack as a hypothetical deck.

Adds non-land spells + lands (Thriving + basics) to deck_expected_cards.
Ensures the Thriving land exists in the collection (adds it if missing).

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-insert-deck.py \
        --color W --theme Angels --description "Angel tribal with lifegain" \
        "Serra Angel" "Angel of Mercy" "Shepherd of the Lost" ...

All positional arguments are card names for the non-land spell slots.
"""

import argparse
import sys

from api_client import DeckBuilderClient, parse_host_arg

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
               "C": "Colorless"}

THRIVING_NAMES = {
    "W": "Thriving Heath", "U": "Thriving Isle", "B": "Thriving Moor",
    "R": "Thriving Bluff", "G": "Thriving Grove",
}

BASIC_NAMES = {
    "W": "Plains", "U": "Island", "B": "Swamp",
    "R": "Mountain", "G": "Forest",
}


def main():
    base_url, argv = parse_host_arg(sys.argv)

    parser = argparse.ArgumentParser(
        description="Insert a Jumpstart pack as a hypothetical deck"
    )
    parser.add_argument("cards", nargs="+", help="Card names (non-land spells)")
    parser.add_argument("--color", required=True, choices=["W", "U", "B", "R", "G", "C"],
                        help="Pack color")
    parser.add_argument("--theme", required=True, help="Pack theme name")
    parser.add_argument("--description", required=True, help="Pack description/synergies")
    parser.add_argument("--basics", type=int, default=7,
                        help="Number of basic lands (default: 7)")
    args = parser.parse_args(argv[1:])

    # Check for duplicate card names
    seen = set()
    for card_name in args.cards:
        if card_name in seen:
            print(f"ERROR: Duplicate card: {card_name}", file=sys.stderr)
            sys.exit(1)
        seen.add(card_name)

    client = DeckBuilderClient(base_url)
    result = client.post("/api/jumpstart/insert-deck", {
        "color": args.color,
        "theme": args.theme,
        "description": args.description,
        "cards": args.cards,
        "basics": args.basics,
    })

    deck_id = result["deck_id"]
    deck_name = result["name"]

    print(f"Created hypothetical deck: {deck_name} (id={deck_id})")
    print(f"Color: {COLOR_NAMES[args.color]}")
    print(f"Spells ({len(args.cards)}):")
    for card_name in args.cards:
        print(f"  {card_name}")
    if args.color == "C":
        print(f"Lands: (no lands — colorless deck, partner provides lands)")
    else:
        thriving_name = THRIVING_NAMES[args.color]
        basic_name = BASIC_NAMES[args.color]
        print(f"Lands:")
        print(f"  1 {thriving_name}")
        print(f"  {args.basics} {basic_name}")


if __name__ == "__main__":
    main()
