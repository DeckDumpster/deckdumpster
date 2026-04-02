#!/usr/bin/env python3
"""Search owned cards using SQL WHERE clauses.

Usage:
  jumpstart-search.py "<sql_where_clause>"
  jumpstart-search.py --schema

Examples:
  jumpstart-search.py "c.type_line LIKE '%Elf%' AND c.colors = '[\"G\"]'"
  jumpstart-search.py "c.oracle_text LIKE '%create%token%' AND c.cmc <= 3"
  jumpstart-search.py "p.rarity IN ('rare', 'mythic') AND c.cmc <= 5"

The WHERE clause has access to these table aliases:
  c   = cards (name, oracle_text, type_line, mana_cost, cmc, colors, color_identity)
  p   = printings (set_code, collector_number, rarity, image_uri, frame_effects, border_color, full_art)
  col = collection (id, finish, condition, status, deck_id, binder_id)

Results are deduplicated by oracle_id and limited to 50.
"""
import sys

from api_client import DeckBuilderClient, parse_host_arg


def count_effects(oracle_text):
    """Count distinct effect types in oracle text as a quality signal."""
    if not oracle_text:
        return 0, []
    text = oracle_text.lower()
    effects = []
    if any(k in text for k in ["draw a card", "draw cards", "draws a card"]):
        effects.append("draw")
    if any(k in text for k in ["gain", "life"]) and "life" in text:
        effects.append("lifegain")
    if any(k in text for k in ["destroy", "exile target", "deals", "damage to"]):
        effects.append("removal")
    if any(k in text for k in ["+1/+1 counter", "gets +", "get +"]):
        effects.append("pump")
    if any(k in text for k in ["create", "token"]) and "token" in text:
        effects.append("tokens")
    if any(k in text for k in ["flying", "vigilance", "lifelink", "first strike",
                                 "deathtouch", "trample", "haste", "reach",
                                 "hexproof", "indestructible", "menace"]):
        effects.append("keywords")
    if any(k in text for k in ["whenever", "when", "at the beginning"]):
        effects.append("trigger")
    if any(k in text for k in ["search your library"]):
        effects.append("tutor")
    if any(k in text for k in ["return", "from your graveyard"]) and "graveyard" in text:
        effects.append("recursion")
    return len(effects), effects


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

where_clause = argv[1]

client = DeckBuilderClient(base_url)
results = client.post("/api/jumpstart/sql-search", {"where_clause": where_clause})

if not results:
    print(f"No cards found matching: {where_clause}")
    sys.exit(0)

print(f"Found {len(results)} candidates:\n")
for card in results:
    rarity = (card.get("rarity") or "?")[0].upper()
    cmc = int(card.get("cmc") or 0)
    name = card.get("name", "?")
    set_code = card.get("set_code", "").upper()
    cn = card.get("collector_number", "")
    type_line = card.get("type_line") or ""
    oracle_text = card.get("oracle_text") or ""

    signals = []
    effect_count, effect_list = count_effects(oracle_text)
    if effect_count >= 2:
        signals.append(f"{effect_count} effects({','.join(effect_list)})")
    signal_str = f"  [{', '.join(signals)}]" if signals else ""

    print(f"  [{rarity}] CMC {cmc}  {name:40s} {set_code}/{cn}{signal_str}")
    print(f"      Type: {type_line}")
    if oracle_text:
        text = oracle_text.replace("\n", " | ")
        if len(text) > 120:
            text = text[:117] + "..."
        print(f"      Text: {text}")
    print()

if len(results) >= 50:
    print("--- Results capped at 50. Add filters to narrow: ---")
    example = f'jumpstart-search.py "{where_clause} AND c.cmc <= 3"'
    print(f"uv run python .claude/skills/jumpstart/scripts/{example}")
