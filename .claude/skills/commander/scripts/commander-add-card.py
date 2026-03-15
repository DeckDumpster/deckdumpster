#!/usr/bin/env python3
"""Add a card to a commander deck with explicit category assignments.

Usage:
  commander-add-card.py <deck_id> <collection_id> --categories "Ramp" "Plan Cards" "+1/+1 Counter Synergy"

Categories can be template roles (Lands, Ramp, Card Advantage, Targeted Disruption,
Mass Disruption, Plan Cards) and/or custom sub-plan names defined during plan creation.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import DeckBuilderService

if len(sys.argv) < 3:
    print("Usage: commander-add-card.py <deck_id> <collection_id> --categories <name> ...")
    sys.exit(1)

deck_id = int(sys.argv[1])
collection_id = int(sys.argv[2])

# Parse --categories (required, all remaining args after the flag)
if "--categories" not in sys.argv:
    print("Error: --categories is required. Specify at least one category.")
    print("  Template roles: Lands, Ramp, \"Card Advantage\", \"Targeted Disruption\", \"Mass Disruption\", \"Plan Cards\"")
    print("  Sub-plan names are also valid (as defined during plan creation).")
    sys.exit(1)

idx = sys.argv.index("--categories")
categories = sys.argv[idx + 1:]
if not categories:
    print("Error: --categories requires at least one category name.")
    sys.exit(1)

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row
svc = DeckBuilderService(conn)

try:
    result = svc.add_card(deck_id, collection_id, categories)
except ValueError as e:
    print(f"Error: {e}")
    conn.close()
    sys.exit(1)

conn.close()

roles_str = ", ".join(result["roles"])
print(f"Added: {result['name']}")
print(f"  Detected roles (hint): {roles_str}")
if result.get("categories"):
    print(f"  Assigned to: {', '.join(result['categories'])}")
print(f"  Deck now has {result['deck_card_count']}/99 cards (+1 Commander)")
