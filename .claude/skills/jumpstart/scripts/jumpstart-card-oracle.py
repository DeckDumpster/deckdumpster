#!/usr/bin/env python3
"""Look up a card's oracle text by name.

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-card-oracle.py "Gravecrawler"
    uv run python .claude/skills/jumpstart/scripts/jumpstart-card-oracle.py "Doom Blade"
"""

import sys

from api_client import DeckBuilderClient, parse_host_arg


def main():
    base_url, argv = parse_host_arg(sys.argv)

    if len(argv) < 2:
        print("Usage: jumpstart-card-oracle.py <card name>", file=sys.stderr)
        sys.exit(1)

    name = " ".join(argv[1:])
    client = DeckBuilderClient(base_url)
    results = client.get("/api/cards/by-name", {"name": name})

    if not results:
        print(f"No card found matching '{name}'")
        sys.exit(1)

    if len(results) > 10:
        print(f"Too many matches ({len(results)}). Be more specific.")
        for r in results[:15]:
            print(f"  {r['name']}")
        sys.exit(1)

    for row in results:
        _print_card(row)
        if len(results) > 1:
            print()


def _print_card(row):
    print(f"{row['name']}  {row.get('mana_cost') or ''}")
    print(f"{row.get('type_line', '')}")
    power = row.get("power")
    toughness = row.get("toughness")
    if power is not None and toughness is not None:
        print(f"{power}/{toughness}")
    if row.get("oracle_text"):
        print("---")
        print(row["oracle_text"])


if __name__ == "__main__":
    main()
