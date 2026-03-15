#!/usr/bin/env python3
"""Save a deck plan/theme and optional sub-plans for a commander deck.

Usage:
  commander-save-plan.py <deck_id> "<plan text>"
  commander-save-plan.py <deck_id> "<plan text>" --sub-plans '<json array>'

Sub-plans JSON format: [{"name": "Reanimation", "target": 12, "search_hint": "return.*from.*graveyard"}, ...]
  - name: display name for the sub-category
  - target: how many cards you want in this sub-category
  - search_hint: text/pattern to match against oracle text, type line, or card name
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import DeckBuilderService

if len(sys.argv) < 3:
    print("Usage: commander-save-plan.py <deck_id> <plan text> [--sub-plans '<json>']")
    sys.exit(1)

deck_id = int(sys.argv[1])
plan = sys.argv[2]

# Parse optional --sub-plans
sub_plans = None
if "--sub-plans" in sys.argv:
    idx = sys.argv.index("--sub-plans")
    if idx + 1 < len(sys.argv):
        sub_plans = json.loads(sys.argv[idx + 1])

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row
svc = DeckBuilderService(conn)

svc.save_plan(deck_id, plan)
if sub_plans:
    svc.save_sub_plans(deck_id, sub_plans)

conn.close()

print(f"Plan saved for deck {deck_id}: {plan}")
if sub_plans:
    print(f"\nSub-plan categories:")
    for sp in sub_plans:
        print(f"  - {sp['name']}: {sp['target']} cards (search: \"{sp['search_hint']}\")")
