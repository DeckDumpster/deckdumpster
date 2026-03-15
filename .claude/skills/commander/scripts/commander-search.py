#!/usr/bin/env python3
"""Search owned cards for a commander deck using SQL WHERE clauses.

Usage:
  commander-search.py <deck_id> "<sql_where_clause>"
  commander-search.py --schema

Examples:
  commander-search.py 62 "c.oracle_text LIKE '%destroy target%' AND c.cmc <= 3"
  commander-search.py 62 "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%enters%' AND c.cmc <= 3"
  commander-search.py 62 "c.name LIKE '%lightning%'"
  commander-search.py 62 "c.oracle_text LIKE '%draw%card%' AND c.cmc <= 4"
  commander-search.py --schema

The WHERE clause has access to these table aliases:
  c  = cards (name, oracle_text, type_line, mana_cost, cmc, colors, color_identity)
  p  = printings (set_code, collector_number, rarity, image_uri, frame_effects, border_color, full_art)
  col = collection (id, finish, condition, status, deck_id, binder_id)

Cards already in the deck (by oracle_id) are excluded automatically.
Color identity is filtered to match the commander.
Results are deduplicated by oracle_id (one printing per card, basics exempt).
EDHREC inclusion rate is shown when data exists for this commander.
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path
from mtg_collector.services.deck_builder import RoleClassifier

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

if sys.argv[1] == "--schema":
    print("=== Available columns ===\n")
    print("cards (c):")
    print("  c.name, c.oracle_text, c.type_line, c.mana_cost, c.cmc,")
    print("  c.colors, c.color_identity, c.oracle_id\n")
    print("printings (p):")
    print("  p.set_code, p.collector_number, p.rarity, p.image_uri,")
    print("  p.frame_effects, p.border_color, p.full_art, p.promo, p.promo_types\n")
    print("collection (col):")
    print("  col.id, col.finish, col.condition, col.status, col.deck_id, col.binder_id\n")
    print("=== Example queries ===\n")
    print('  "c.oracle_text LIKE \'%destroy target%\' AND c.cmc <= 3"')
    print('  "c.type_line LIKE \'%Creature%\' AND c.cmc <= 2"')
    print('  "c.oracle_text LIKE \'%sacrifice%\' AND c.oracle_text LIKE \'%draw%\'"')
    print('  "p.rarity IN (\'rare\', \'mythic\') AND c.cmc <= 4"')
    sys.exit(0)

if len(sys.argv) < 3:
    print("Usage: commander-search.py <deck_id> \"<sql_where_clause>\"")
    sys.exit(1)

deck_id = int(sys.argv[1])
where_clause = sys.argv[2]

# Safety: block statement injection (semicolons) and dangerous operations.
# The WHERE clause is interpolated into a SELECT, so the risk is new statements
# or pragmas. String content like '%create%Treasure%' is safe.
if ";" in where_clause:
    print("Error: semicolons are not allowed in WHERE clauses.")
    sys.exit(1)
if re.search(r"\b(ATTACH|DETACH|PRAGMA)\b", where_clause, re.IGNORECASE):
    print("Error: only read-only WHERE clauses are allowed.")
    sys.exit(1)

BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest",
                    "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
                    "Snow-Covered Swamp", "Snow-Covered Mountain",
                    "Snow-Covered Forest"}

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row

# Get deck info
deck = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
if not deck:
    print(f"Deck not found: {deck_id}")
    sys.exit(1)

# Commander color identity
cmd_colors = []
if deck["commander_oracle_id"]:
    row = conn.execute(
        "SELECT color_identity FROM cards WHERE oracle_id = ?",
        (deck["commander_oracle_id"],),
    ).fetchone()
    if row and row["color_identity"]:
        ci_raw = row["color_identity"]
        cmd_colors = json.loads(ci_raw) if isinstance(ci_raw, str) else ci_raw

# Cards already in deck (by oracle_id for singleton check)
from mtg_collector.db.models import DeckRepository
repo = DeckRepository(conn)
in_deck_oracle = {c["oracle_id"] for c in repo.get_cards(deck_id) if c.get("oracle_id")}

# EDHREC data
edhrec_map = {}
table_check = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='edhrec_recommendations'"
).fetchone()
if table_check and deck["commander_oracle_id"]:
    erecs = conn.execute(
        "SELECT card_oracle_id, inclusion_rate, synergy_score FROM edhrec_recommendations WHERE commander_oracle_id = ?",
        (deck["commander_oracle_id"],),
    ).fetchall()
    edhrec_map = {r["card_oracle_id"]: dict(r) for r in erecs}

# Build and execute query
sql = f"""SELECT col.id, col.printing_id, col.finish, col.condition,
                 p.set_code, p.collector_number, p.rarity, p.image_uri,
                 p.frame_effects, p.border_color, p.full_art, p.promo, p.promo_types,
                 c.name, c.type_line, c.mana_cost, c.cmc,
                 c.color_identity, c.oracle_id, c.oracle_text
          FROM collection col
          JOIN printings p ON col.printing_id = p.printing_id
          JOIN cards c ON p.oracle_id = c.oracle_id
          WHERE col.status = 'owned'
            AND ({where_clause})
          ORDER BY c.cmc, c.name
          LIMIT 200"""

try:
    rows = conn.execute(sql).fetchall()
except sqlite3.OperationalError as e:
    print(f"SQL error: {e}")
    print(f"\nQuery was: WHERE {where_clause}")
    print("\nRun with --schema to see available columns.")
    conn.close()
    sys.exit(1)

classifier = RoleClassifier()
results = []
seen_oracle = set()

for r in rows:
    card = dict(r)
    oid = card["oracle_id"]
    is_basic = card.get("name", "") in BASIC_LAND_NAMES

    # Skip cards already in deck (singleton, basics exempt)
    if oid in in_deck_oracle and not is_basic:
        continue

    # Skip duplicate printings (basics exempt)
    if oid in seen_oracle and not is_basic:
        continue

    # Color identity filter
    card_ci = json.loads(card["color_identity"]) if isinstance(card["color_identity"], str) and card["color_identity"] else []
    if card_ci and cmd_colors:
        if not set(card_ci).issubset(set(cmd_colors)):
            continue

    card["roles"] = classifier.classify(card)
    erec = edhrec_map.get(oid)
    if erec:
        card["edhrec_rate"] = erec.get("inclusion_rate")

    seen_oracle.add(oid)
    results.append(card)
    if len(results) >= 50:
        break

conn.close()

if not results:
    print(f"No cards found matching: {where_clause}")
    sys.exit(0)

print(f"Found {len(results)} candidates:\n")
for card in results:
    rarity = (card.get("rarity") or "?")[0].upper()
    cmc = int(card.get("cmc") or 0)
    roles_str = ", ".join(card.get("roles", []))
    edhrec_str = ""
    if card.get("edhrec_rate"):
        edhrec_str = f" [EDHREC {card['edhrec_rate']:.0%}]"

    # Special treatment indicators
    treatments = []
    frame_effects = card.get("frame_effects") or ""
    if "extendedart" in frame_effects:
        treatments.append("Extended Art")
    if "showcase" in frame_effects:
        treatments.append("Showcase")
    border = card.get("border_color") or ""
    if border == "borderless":
        treatments.append("Borderless")
    if card.get("full_art"):
        treatments.append("Full Art")
    treat_str = f" [{', '.join(treatments)}]" if treatments else ""

    print(f"  [{rarity}] {card['name']} (CMC {cmc}) — {card.get('set_code','').upper()}/{card.get('collector_number','')}")
    print(f"      Type: {card.get('type_line', '?')}")
    print(f"      Role hints: {roles_str}{edhrec_str}{treat_str}")
    print(f"      collection_id: {card['id']}")
    oracle = card.get("oracle_text") or ""
    if oracle:
        if len(oracle) > 150:
            oracle = oracle[:147] + "..."
        print(f"      Text: {oracle}")
    print()
