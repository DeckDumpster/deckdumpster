#!/usr/bin/env python3
"""Create a new commander deck.

Usage: uv run python .claude/skills/commander/scripts/commander-create-deck.py "<commander name query>"

Searches the collection for legendary creatures matching the query,
then creates a hypothetical commander deck for the best match.
If multiple matches, prints all and exits — re-run with a more specific query.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import DeckBuilderService

query = sys.argv[1] if len(sys.argv) > 1 else ""
if not query:
    print("Usage: commander-create-deck.py <commander name query>")
    sys.exit(1)

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row
svc = DeckBuilderService(conn)

matches = svc.find_commanders(query)
if not matches:
    print(f"No legendary creatures found matching '{query}' in your collection.")
    conn.close()
    sys.exit(1)

if len(matches) > 1:
    print(f"Multiple commanders match '{query}':")
    for m in matches:
        ci = m["color_identity"] or "[]"
        print(f"  {m['name']} ({m['mana_cost']}) — Color Identity: {ci}")
        print(f"    oracle_id: {m['oracle_id']}")
    print("\nRe-run with a more specific query or use oracle_id directly.")
    conn.close()
    sys.exit(0)

match = matches[0]
result = svc.create_deck(match["oracle_id"])
conn.close()

print(f"Created deck: {result['name']}")
print(f"  Deck ID: {result['deck_id']}")
print(f"  Color Identity: {result['color_identity']}")
print(f"  Format: Commander (hypothetical)")
