#!/usr/bin/env python3
"""Upgrade deck cards to the blingiest printings you own.

Usage:
  commander-bling-it-up.py <deck_id> [--dry-run]

For each card in the deck, finds all printings you own (by oracle_id) and
swaps to the blingiest one. Bling ranking:

  1. Borderless border
  2. Full art
  3. Showcase frame
  4. Extended art frame
  5. Foil finish
  6. Promo
  7. Standard frame (no bling)

Ties broken by: foil > nonfoil, then collection_id DESC (newer).
"""
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

if len(argv) < 2:
    print("Usage: commander-bling-it-up.py <deck_id> [--dry-run]")
    sys.exit(1)

deck_id = int(argv[1])
dry_run = "--dry-run" in argv

client = DeckBuilderClient(base_url)
result = client.post(f"/api/deck-builder/{deck_id}/bling", {"dry_run": dry_run})

swaps = result.get("swaps", [])
if not swaps:
    print("Already at maximum bling! No upgrades found.")
    sys.exit(0)

print(f"Found {len(swaps)} bling upgrade{'s' if len(swaps) != 1 else ''}:\n")
for s in swaps:
    tags = ", ".join(s.get("bling_tags", [])) or "standard"
    print(f"  {s['name']}")
    print(f"    {s['old_set']} ({s['old_finish']}, score {s['old_score']})")
    print(f"    → {s['new_set']} ({s['new_finish']}, score {s['new_score']}) [{tags}]")

if dry_run:
    print(f"\n[dry-run] No changes made. Run without --dry-run to apply.")
elif result.get("applied"):
    print(f"\nApplied {len(swaps)} bling upgrade{'s' if len(swaps) != 1 else ''}.")
