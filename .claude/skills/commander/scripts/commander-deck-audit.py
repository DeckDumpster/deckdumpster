#!/usr/bin/env python3
"""Audit a commander deck against the Command Zone 2025 template.

Usage: uv run python .claude/skills/commander/scripts/commander-deck-audit.py <deck_id>
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import DeckBuilderService

if len(sys.argv) < 2:
    print("Usage: commander-deck-audit.py <deck_id>")
    sys.exit(1)

deck_id = int(sys.argv[1])

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row
svc = DeckBuilderService(conn)

audit = svc.audit(deck_id)
conn.close()

# Format output
ci_str = "/".join(audit["color_identity"]) if audit["color_identity"] else "Colorless"
print(f"=== Deck Audit: {audit['commander'] or audit['name']} ===")
print(f"Cards: {audit['card_count']}/99 (+1 Commander)")
print(f"Plan: {audit['plan'] or '(no plan set)'}")
print(f"Color Identity: {ci_str}")

print("\n--- Role Distribution (Command Zone 2025 Template) ---")
print(f"{'Category':<22} {'Have':>4}  {'Target':>6}  Status")
for role, info in audit["template"].items():
    print(f"{role:<22} {info['have']:>4}  {info['target']:>6}   {info['status']}")

if audit.get("sub_plans"):
    print("\n--- Sub-Plan Categories ---")
    print(f"{'Category':<30} {'Have':>4}  {'Target':>6}  Status")
    for sp in audit["sub_plans"]:
        print(f"{sp['name']:<30} {sp['have']:>4}  {sp['target']:>6}   {sp['status']}")
        if sp["matched"]:
            for name in sp["matched"]:
                print(f"  - {name}")

print("\n--- Mana Curve (non-land) ---")
for cmc in range(8):
    count = audit["curve"].get(cmc, 0)
    label = f"CMC {cmc}" if cmc < 7 else "CMC 7+"
    bar = "#" * count
    print(f"{label}: {bar} ({count})")

if audit["edhrec"]:
    print("\n--- EDHREC Recommendations (owned, not in deck) ---")
    for rec in audit["edhrec"][:10]:
        rate = rec.get("inclusion_rate")
        rate_str = f"{rate:.0%}" if rate else "??%"
        print(f"{rate_str} {rec['name']} (collection #{rec['collection_id']})")

if audit["next_priority"]:
    print(f"\n>>> NEXT PRIORITY: Add {audit['next_priority']} (need {audit['next_priority_gap']} more)")

if audit["card_count"] >= 99:
    print("\n>>> DECK IS COMPLETE! (99 cards + commander)")
