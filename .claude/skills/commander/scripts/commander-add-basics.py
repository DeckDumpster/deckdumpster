#!/usr/bin/env python3
"""Bulk-add basic lands to a commander deck.

Usage:
  commander-add-basics.py <deck_id> --plains N --island N --forest N [--mountain N] [--swamp N]

Finds collection entries for basics and adds them with the "Lands" category.
Prefers full-art printings, then the set matching the commander's set.
"""
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

BASIC_NAMES = {"plains", "island", "forest", "mountain", "swamp"}

if len(argv) < 2:
    print("Usage: commander-add-basics.py <deck_id> --plains N --island N --forest N")
    sys.exit(1)

deck_id = int(argv[1])

# Parse --<basic> N pairs
counts = {}
i = 2
while i < len(argv):
    arg = argv[i].lstrip("-").lower()
    if arg in BASIC_NAMES and i + 1 < len(argv):
        counts[arg] = int(argv[i + 1])
        i += 2
    else:
        i += 1

if not counts:
    print("Error: specify at least one basic land count (e.g. --plains 8)")
    sys.exit(1)

client = DeckBuilderClient(base_url)
result = client.post(f"/api/deck-builder/{deck_id}/add-basics", counts)

for name, info in result.get("basics", {}).items():
    full_art_str = f" ({info['full_art']} full-art)" if info.get("full_art") else ""
    print(f"  {name}: added {info['added']}/{info['requested']}{full_art_str}")

print(f"\nDeck now has {result['deck_card_count']}/99 cards (+1 Commander)")
