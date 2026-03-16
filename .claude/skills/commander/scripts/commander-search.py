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
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

if len(argv) < 2:
    print(__doc__)
    sys.exit(1)

if argv[1] == "--schema":
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

if len(argv) < 3:
    print("Usage: commander-search.py <deck_id> \"<sql_where_clause>\"")
    sys.exit(1)

deck_id = int(argv[1])
where_clause = argv[2]

client = DeckBuilderClient(base_url)
results = client.post(f"/api/deck-builder/{deck_id}/sql-search", {
    "where_clause": where_clause,
})

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

    print(f"  [{rarity}] {card['name']} (CMC {cmc}) — {card.get('set_code', '').upper()}/{card.get('collector_number', '')}")
    print(f"      Type: {card.get('type_line', '?')}")
    print(f"      Role hints: {roles_str}{edhrec_str}{treat_str}")
    print(f"      collection_id: {card['id']}")
    oracle = card.get("oracle_text") or ""
    if oracle:
        print(f"      Text: {oracle}")
    print()
