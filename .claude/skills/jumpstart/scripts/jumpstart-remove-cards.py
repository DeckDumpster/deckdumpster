#!/usr/bin/env python3
"""Remove cards from a Jumpstart idea deck by name.

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-remove-cards.py \
        --deck 22 "Cobra Trap" "Savage Thallid" "Ice Cream Kitty"
"""

import argparse
import sys

from api_client import DeckBuilderClient, parse_host_arg


def main():
    base_url, argv = parse_host_arg(sys.argv)

    parser = argparse.ArgumentParser(
        description="Remove cards from a hypothetical Jumpstart deck"
    )
    parser.add_argument("cards", nargs="+", help="Card names to remove")
    parser.add_argument("--deck", required=True, type=int, help="Deck ID")
    args = parser.parse_args(argv[1:])

    client = DeckBuilderClient(base_url)

    # Fetch current deck cards to map names → printing_ids
    deck_cards = client.get(f"/api/decks/{args.deck}/cards")
    name_to_pid = {}
    for c in deck_cards:
        name_to_pid[c["name"]] = c["printing_id"]

    removed = []
    not_found = []
    for name in args.cards:
        pid = name_to_pid.get(name)
        if not pid:
            not_found.append(name)
            continue
        client.post(
            f"/api/decks/{args.deck}/expected-cards/remove",
            {"printing_id": pid},
        )
        removed.append(name)

    if removed:
        print(f"Removed {len(removed)} cards from deck {args.deck}:")
        for name in removed:
            print(f"  - {name}")

    if not_found:
        print(f"\nNot found in deck ({len(not_found)}):")
        for name in not_found:
            print(f"  ? {name}")

    # Show remaining count
    remaining = client.get(f"/api/decks/{args.deck}/cards")
    non_land = [c for c in remaining if "Land" not in (c.get("type_line") or "")
                or "Basic" not in (c.get("type_line") or "")]
    print(f"\nDeck now has {len(remaining)} cards total")


if __name__ == "__main__":
    main()
