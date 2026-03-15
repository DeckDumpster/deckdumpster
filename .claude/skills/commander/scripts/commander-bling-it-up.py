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
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path


def bling_score(row):
    """Score a printing+collection entry. Higher = blingier."""
    frame_effects = json.loads(row["frame_effects"]) if row["frame_effects"] else []
    promo_types = json.loads(row["promo_types"]) if row["promo_types"] else []
    score = 0
    if row["border_color"] == "borderless":
        score += 100
    if row["full_art"]:
        score += 80
    if "showcase" in frame_effects:
        score += 60
    if "extendedart" in frame_effects:
        score += 40
    # Serialized, doublerainbow, etc. are ultra-premium
    if "serialized" in promo_types:
        score += 200
    if "doublerainbow" in promo_types:
        score += 150
    if row["finish"] == "foil":
        score += 20
    if row["promo"]:
        score += 10
    return score


def main():
    if len(sys.argv) < 2:
        print("Usage: commander-bling-it-up.py <deck_id> [--dry-run]")
        sys.exit(1)

    deck_id = int(sys.argv[1])
    dry_run = "--dry-run" in sys.argv

    conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
    conn.row_factory = sqlite3.Row

    # Get all cards currently in the deck
    deck_cards = conn.execute("""
        SELECT col.id as collection_id, col.printing_id, col.finish,
               c.oracle_id, c.name,
               p.frame_effects, p.promo_types, p.border_color,
               p.full_art, p.promo, p.set_code, p.collector_number
        FROM collection col
        JOIN printings p ON col.printing_id = p.printing_id
        JOIN cards c ON p.oracle_id = c.oracle_id
        WHERE col.deck_id = ?
    """, (deck_id,)).fetchall()

    if not deck_cards:
        print(f"No cards found in deck {deck_id}")
        sys.exit(1)

    # Load sub_plans for category reference updates
    deck = conn.execute("SELECT sub_plans FROM decks WHERE id = ?", (deck_id,)).fetchone()
    sub_plans = json.loads(deck["sub_plans"]) if deck and deck["sub_plans"] else []

    # Check if deck is hypothetical
    is_hypo = conn.execute(
        "SELECT hypothetical FROM decks WHERE id = ?", (deck_id,)).fetchone()
    hypothetical = is_hypo and is_hypo["hypothetical"]

    swaps = []
    # Track collection_ids already claimed (in deck or pending swap)
    # to avoid assigning the same physical card to multiple deck slots
    claimed_ids = {card["collection_id"] for card in deck_cards}
    for card in deck_cards:
        current_score = bling_score(card)
        oracle_id = card["oracle_id"]

        # Find all owned printings of same card (by oracle_id)
        if hypothetical:
            # Hypothetical decks can use cards from anywhere
            candidates = conn.execute("""
                SELECT col.id as collection_id, col.printing_id, col.finish,
                       p.frame_effects, p.promo_types, p.border_color,
                       p.full_art, p.promo, p.set_code, p.collector_number
                FROM collection col
                JOIN printings p ON col.printing_id = p.printing_id
                WHERE p.oracle_id = ? AND col.status = 'owned'
                  AND col.id != ?
                  AND col.id NOT IN (
                      SELECT id FROM collection WHERE deck_id = ?
                  )
            """, (oracle_id, card["collection_id"], deck_id)).fetchall()
        else:
            candidates = conn.execute("""
                SELECT col.id as collection_id, col.printing_id, col.finish,
                       p.frame_effects, p.promo_types, p.border_color,
                       p.full_art, p.promo, p.set_code, p.collector_number
                FROM collection col
                JOIN printings p ON col.printing_id = p.printing_id
                WHERE p.oracle_id = ? AND col.status = 'owned'
                  AND col.id != ?
                  AND col.deck_id IS NULL AND col.binder_id IS NULL
            """, (oracle_id, card["collection_id"])).fetchall()

        # Filter out collection_ids already claimed by this deck or pending swaps
        candidates = [c for c in candidates if c["collection_id"] not in claimed_ids]

        if not candidates:
            continue

        # Find blingiest candidate
        best = max(candidates, key=lambda r: (bling_score(r), r["collection_id"]))
        best_score = bling_score(best)

        if best_score > current_score:
            # Claim the new ID and release the old one
            claimed_ids.add(best["collection_id"])
            claimed_ids.discard(card["collection_id"])
            swaps.append({
                "name": card["name"],
                "old_id": card["collection_id"],
                "new_id": best["collection_id"],
                "old_set": f"{card['set_code']}/{card['collector_number']}",
                "new_set": f"{best['set_code']}/{best['collector_number']}",
                "old_score": current_score,
                "new_score": best_score,
                "old_finish": card["finish"],
                "new_finish": best["finish"],
                "bling_tags": _bling_tags(best),
            })

    if not swaps:
        print("Already at maximum bling! No upgrades found.")
        conn.close()
        return

    print(f"Found {len(swaps)} bling upgrade{'s' if len(swaps) != 1 else ''}:\n")
    for s in swaps:
        tags = ", ".join(s["bling_tags"]) if s["bling_tags"] else "standard"
        print(f"  {s['name']}")
        print(f"    {s['old_set']} ({s['old_finish']}, score {s['old_score']})")
        print(f"    → {s['new_set']} ({s['new_finish']}, score {s['new_score']}) [{tags}]")

    if dry_run:
        print(f"\n[dry-run] No changes made. Run without --dry-run to apply.")
        conn.close()
        return

    # Apply swaps
    for s in swaps:
        old_id = s["old_id"]
        new_id = s["new_id"]

        # Remove old from deck
        conn.execute(
            "UPDATE collection SET deck_id = NULL, deck_zone = NULL WHERE id = ?",
            (old_id,))
        # Add new to deck
        conn.execute(
            "UPDATE collection SET deck_id = ?, deck_zone = 'mainboard' WHERE id = ?",
            (deck_id, new_id))

        # Update sub_plans references
        for sp in sub_plans:
            cards = sp.get("cards", [])
            if old_id in cards:
                cards[cards.index(old_id)] = new_id

    # Save updated sub_plans
    if sub_plans:
        conn.execute(
            "UPDATE decks SET sub_plans = ? WHERE id = ?",
            (json.dumps(sub_plans), deck_id))

    conn.commit()
    conn.close()

    print(f"\nApplied {len(swaps)} bling upgrade{'s' if len(swaps) != 1 else ''}.")


def _bling_tags(row):
    """Return human-readable bling tags for a printing."""
    tags = []
    frame_effects = json.loads(row["frame_effects"]) if row["frame_effects"] else []
    promo_types = json.loads(row["promo_types"]) if row["promo_types"] else []
    if row["border_color"] == "borderless":
        tags.append("Borderless")
    if row["full_art"]:
        tags.append("Full Art")
    if "showcase" in frame_effects:
        tags.append("Showcase")
    if "extendedart" in frame_effects:
        tags.append("Extended Art")
    if "serialized" in promo_types:
        tags.append("Serialized")
    if "doublerainbow" in promo_types:
        tags.append("Double Rainbow")
    if row["finish"] == "foil":
        tags.append("Foil")
    if row["promo"]:
        tags.append("Promo")
    return tags


if __name__ == "__main__":
    main()
