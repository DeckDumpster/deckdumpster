#!/usr/bin/env python3
"""Bulk-add basic lands to a commander deck.

Usage:
  commander-add-basics.py <deck_id> --plains N --island N --forest N [--mountain N] [--swamp N]

Finds collection entries for basics and adds them with the "Lands" category.
Prefers full-art printings, then the set matching the commander's set.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import DeckBuilderService

BASIC_NAMES = {"plains": "Plains", "island": "Island", "forest": "Forest",
               "mountain": "Mountain", "swamp": "Swamp"}

if len(sys.argv) < 2:
    print("Usage: commander-add-basics.py <deck_id> --plains N --island N --forest N")
    sys.exit(1)

deck_id = int(sys.argv[1])

# Parse --<basic> N pairs
counts = {}
i = 2
while i < len(sys.argv):
    arg = sys.argv[i].lstrip("-").lower()
    if arg in BASIC_NAMES and i + 1 < len(sys.argv):
        counts[BASIC_NAMES[arg]] = int(sys.argv[i + 1])
        i += 2
    else:
        i += 1

if not counts:
    print("Error: specify at least one basic land count (e.g. --plains 8)")
    sys.exit(1)

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row
svc = DeckBuilderService(conn)

# Get commander's set for preferred printing
deck = conn.execute("SELECT origin_set_code FROM decks WHERE id = ?", (deck_id,)).fetchone()
preferred_set = deck["origin_set_code"] if deck and deck["origin_set_code"] else None

# Get existing card IDs in deck to avoid re-adding same collection entry
existing = {r["id"] for r in conn.execute(
    "SELECT id FROM collection WHERE deck_id = ?", (deck_id,)).fetchall()}

total_added = 0
for name, count in counts.items():
    # Find available collection entries for this basic, ranked by preference
    rows = conn.execute("""
        SELECT col.id, p.set_code, p.full_art
        FROM collection col
        JOIN printings p ON col.printing_id = p.printing_id
        JOIN cards c ON p.oracle_id = c.oracle_id
        WHERE c.name = ? AND col.status = 'owned'
          AND col.id NOT IN (SELECT id FROM collection WHERE deck_id IS NOT NULL)
        ORDER BY
          p.full_art DESC,
          CASE WHEN p.set_code = ? THEN 0 ELSE 1 END,
          col.id
    """, (name, preferred_set)).fetchall()

    if len(rows) < count:
        # Also include cards in other decks (hypothetical allows this)
        rows = conn.execute("""
            SELECT col.id, p.set_code, p.full_art
            FROM collection col
            JOIN printings p ON col.printing_id = p.printing_id
            JOIN cards c ON p.oracle_id = c.oracle_id
            WHERE c.name = ? AND col.status = 'owned'
              AND col.id NOT IN (SELECT id FROM collection WHERE deck_id = ?)
            ORDER BY
              p.full_art DESC,
              CASE WHEN p.set_code = ? THEN 0 ELSE 1 END,
              col.id
        """, (name, deck_id, preferred_set)).fetchall()

    added = 0
    for row in rows:
        if added >= count:
            break
        if row["id"] in existing:
            continue
        try:
            svc.add_card(deck_id, row["id"], ["Lands"])
            existing.add(row["id"])
            added += 1
        except ValueError:
            continue

    total_added += added
    full_art_count = sum(1 for r in rows[:added] if r["full_art"])
    print(f"  {name}: added {added}/{count}" +
          (f" ({full_art_count} full-art)" if full_art_count else ""))

# Final count
card_count = conn.execute(
    "SELECT COUNT(*) FROM collection WHERE deck_id = ?", (deck_id,)).fetchone()[0]
conn.close()
print(f"\nDeck now has {card_count}/99 cards (+1 Commander)")
