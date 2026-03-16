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
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

if len(argv) < 3:
    print("Usage: commander-save-plan.py <deck_id> <plan text> [--sub-plans '<json>']")
    sys.exit(1)

deck_id = int(argv[1])
plan = argv[2]

# Parse optional --sub-plans
sub_plans = None
if "--sub-plans" in argv:
    idx = argv.index("--sub-plans")
    if idx + 1 < len(argv):
        sub_plans = json.loads(argv[idx + 1])

client = DeckBuilderClient(base_url)
body = {"plan": plan}
if sub_plans:
    body["sub_plans"] = sub_plans

client.put(f"/api/deck-builder/{deck_id}/plan", body)

print(f"Plan saved for deck {deck_id}: {plan}")
if sub_plans:
    print(f"\nSub-plan categories:")
    for sp in sub_plans:
        print(f"  - {sp['name']}: {sp['target']} cards (search: \"{sp.get('search_hint', '')}\")")
