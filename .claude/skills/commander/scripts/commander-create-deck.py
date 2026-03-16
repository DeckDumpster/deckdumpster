#!/usr/bin/env python3
"""Create a new commander deck.

Usage: uv run python .claude/skills/commander/scripts/commander-create-deck.py "<commander name query>"

Searches the collection for legendary creatures matching the query,
then creates a hypothetical commander deck for the best match.
If multiple matches, prints all and exits — re-run with a more specific query.
"""
import json
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

query = argv[1] if len(argv) > 1 else ""
if not query:
    print("Usage: commander-create-deck.py <commander name query>")
    sys.exit(1)

client = DeckBuilderClient(base_url)

# Search for commanders
matches = client.get("/api/deck-builder/commanders", {"q": query})
if not matches:
    print(f"No legendary creatures found matching '{query}' in your collection.")
    sys.exit(1)

if len(matches) > 1:
    print(f"Multiple commanders match '{query}':")
    for m in matches:
        ci = m.get("color_identity") or "[]"
        print(f"  {m['name']} ({m.get('mana_cost', '')}) — Color Identity: {ci}")
        print(f"    oracle_id: {m['oracle_id']}")
    print("\nRe-run with a more specific query or use oracle_id directly.")
    sys.exit(0)

match = matches[0]
result = client.post("/api/deck-builder", {
    "commander_oracle_id": match["oracle_id"],
    "hypothetical": True,
})

# Server returns {deck_id, name, color_identity} for hypothetical decks
deck_name = result.get("name", match.get("name", "Unknown"))
deck_id = result.get("deck_id", result.get("id", "?"))
ci = result.get("color_identity", match.get("color_identity", "[]"))

print(f"Created deck: {deck_name}")
print(f"  Deck ID: {deck_id}")
print(f"  Color Identity: {ci}")
print(f"  Format: Commander (hypothetical)")
