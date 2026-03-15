#!/usr/bin/env python3
"""Insert a finished Jumpstart pack as a hypothetical deck.

Adds non-land spells + lands (Thriving + basics) to deck_expected_cards.
Ensures the Thriving land exists in the collection (adds it if missing).

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-insert-deck.py \
        --color W --theme Angels --description "Angel tribal with lifegain" \
        "Serra Angel" "Angel of Mercy" "Shepherd of the Lost" ...

All positional arguments are card names for the non-land spell slots.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.utils import now_iso


COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}

THRIVING_NAMES = {
    "W": "Thriving Heath",
    "U": "Thriving Isle",
    "B": "Thriving Moor",
    "R": "Thriving Bluff",
    "G": "Thriving Grove",
}

BASIC_NAMES = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}


def resolve_card(conn, card_name):
    """Resolve a card name to its oracle_id."""
    row = conn.execute(
        "SELECT oracle_id FROM cards WHERE name = ?", (card_name,)
    ).fetchone()
    if not row:
        print(f"ERROR: Card not found in database: {card_name}", file=sys.stderr)
        sys.exit(1)
    return row[0]


def ensure_in_collection(conn, card_name):
    """Add a card to the collection if no owned copy exists. Returns the printing_id used."""
    oracle_id = resolve_card(conn, card_name)

    # Check if already owned
    existing = conn.execute(
        """SELECT col.id FROM collection col
           JOIN printings p ON col.printing_id = p.printing_id
           WHERE p.oracle_id = ? AND col.status = 'owned'
           LIMIT 1""",
        (oracle_id,),
    ).fetchone()
    if existing:
        return

    # Find a printing to add (prefer non-digital, most recent)
    printing = conn.execute(
        """SELECT p.printing_id FROM printings p
           JOIN sets s ON s.set_code = p.set_code
           WHERE p.oracle_id = ? AND s.digital = 0
           ORDER BY s.released_at DESC LIMIT 1""",
        (oracle_id,),
    ).fetchone()
    if not printing:
        print(f"WARNING: No non-digital printing found for {card_name}", file=sys.stderr)
        return

    ts = now_iso()
    conn.execute(
        """INSERT INTO collection (printing_id, finish, status, source, acquired_at)
           VALUES (?, 'nonfoil', 'owned', 'manual', ?)""",
        (printing[0], ts),
    )
    print(f"  Added to collection: {card_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Insert a Jumpstart pack as a hypothetical deck"
    )
    parser.add_argument("cards", nargs="+", help="Card names (non-land spells)")
    parser.add_argument("--color", required=True, choices=["W", "U", "B", "R", "G"],
                        help="Pack color")
    parser.add_argument("--theme", required=True, help="Pack theme name")
    parser.add_argument("--description", required=True, help="Pack description/synergies")
    parser.add_argument("--basics", type=int, default=7,
                        help="Number of basic lands (default: 7)")
    args = parser.parse_args()

    # Check for duplicate card names
    seen = set()
    for card_name in args.cards:
        if card_name in seen:
            print(f"ERROR: Duplicate card: {card_name}", file=sys.stderr)
            sys.exit(1)
        seen.add(card_name)

    conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))

    # Resolve non-land spell cards
    expected_cards = []
    for card_name in args.cards:
        oracle_id = resolve_card(conn, card_name)
        expected_cards.append({
            "oracle_id": oracle_id,
            "zone": "mainboard",
            "quantity": 1,
            "name": card_name,
        })

    # Resolve lands
    thriving_name = THRIVING_NAMES[args.color]
    basic_name = BASIC_NAMES[args.color]
    basic_count = args.basics

    thriving_oracle_id = resolve_card(conn, thriving_name)
    basic_oracle_id = resolve_card(conn, basic_name)

    # Ensure thriving land is in collection
    ensure_in_collection(conn, thriving_name)

    expected_cards.append({
        "oracle_id": thriving_oracle_id,
        "zone": "mainboard",
        "quantity": 1,
        "name": thriving_name,
    })
    expected_cards.append({
        "oracle_id": basic_oracle_id,
        "zone": "mainboard",
        "quantity": basic_count,
        "name": basic_name,
    })

    deck_name = f"{args.theme} (Jumpstart)"

    # Check for existing deck with same name
    existing = conn.execute(
        "SELECT id FROM decks WHERE name = ?", (deck_name,)
    ).fetchone()
    if existing:
        print(f"ERROR: Deck '{deck_name}' already exists (id={existing[0]})", file=sys.stderr)
        sys.exit(1)

    ts = now_iso()
    conn.execute(
        """INSERT INTO decks (name, description, format, hypothetical,
           origin_set_code, origin_theme, is_precon, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            deck_name,
            args.description,
            "jumpstart",
            1,
            "J25",
            args.theme,
            0,
            ts,
            ts,
        ),
    )
    deck_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Insert expected cards
    for card in expected_cards:
        conn.execute(
            """INSERT INTO deck_expected_cards (deck_id, oracle_id, zone, quantity)
               VALUES (?, ?, ?, ?)""",
            (deck_id, card["oracle_id"], card["zone"], card["quantity"]),
        )

    conn.commit()
    conn.close()

    print(f"Created hypothetical deck: {deck_name} (id={deck_id})")
    print(f"Color: {COLOR_NAMES[args.color]}")
    print(f"Spells ({len(args.cards)}):")
    for card_name in args.cards:
        print(f"  {card_name}")
    print(f"Lands:")
    print(f"  1 {thriving_name}")
    print(f"  {basic_count} {basic_name}")


if __name__ == "__main__":
    main()
