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

# --- Card confirmation ---
print(f"Added: {result['name']} [{', '.join(result['categories'])}]")

# --- Abbreviated audit (for AI consumption) ---
audit = result["audit"]
nonland = audit["nonland_count"]

if nonland >= 61:
    print(f"\n>>> 61 NONLAND CARDS COMPLETE ({nonland}/61). Proceed to Phase 4 — run commander-mana-analysis.py {deck_id}")
    sys.exit(0)

# Curve: inline format for AI
CURVE_TARGETS = {0: 0, 1: 5, 2: 17, 3: 17, 4: 12, 5: 7, 6: 10}
curve_parts = []
for cmc in range(7):
    count = audit["curve"].get(cmc, 0)
    if cmc == 6:
        count += audit["curve"].get(7, 0)
        label = "6+"
    else:
        label = str(cmc)
    target = CURVE_TARGETS[cmc]
    if target > 0:
        curve_parts.append(f"CMC{label}:{count}/{target}")
print(f"\nNonland: {nonland}/61 | {' '.join(curve_parts)}")

# Next priority
if audit["next_priority"]:
    print(f"IMPORTANT: Next priority category: {audit['next_priority']} (need {audit['next_priority_gap']} more)")

# Phase-dependent selection criteria
if nonland < 30:
    print("Prefer high-impact win conditions, rares/mythics, high EDHREC inclusion, multi-effect cards")
elif nonland < 50:
    print("Deck is about half done: Fill in curve gaps, prefer multi-role cards (2+ categories), multi-effect over single-effect")
else:
    print("Deck is nearly done: Try to fill curve gaps above and least-filled categories")
    # Show category breakdown in late phase
    for role, info in audit["template"].items():
        if role == "Lands":
            continue
        print(f"  {role}: {info['have']}/{info['target']} {info['status']}")
    if audit.get("sub_plans"):
        for sp in audit["sub_plans"]:
            print(f"  {sp['name']}: {sp['have']}/{sp['target']} {sp['status']}")
