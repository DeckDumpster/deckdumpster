#!/usr/bin/env python3
"""Find cards in the local DB matching a card shape (MV, color, rarity, type).

Shows card quality signals: price, rarity, and multi-effect indicators.

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -m 3 -c W -r common -t Creature -o
    uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -m 2 -c B -r rare -t Creature -o
    uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -m 4 -c W -r uncommon -o --theme angel
    uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -m 2 -c W -o --theme "gain life"

All flags are optional filters — omit any to leave it unconstrained.
At least one filter is required. Use -o to filter to owned cards.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path


def build_query(args):
    """Build SQL query and params from CLI args."""
    conditions = []
    params = []

    # Only paper cards from non-digital sets
    conditions.append("s.digital = 0")

    if args.rarity:
        conditions.append("p.rarity = ?")
        params.append(args.rarity.lower())

    if args.type:
        type_map = {
            "creature": "Creature",
            "instant": "Instant",
            "sorcery": "Sorcery",
            "enchantment": "Enchantment",
            "artifact": "Artifact",
            "planeswalker": "Planeswalker",
        }
        card_type = type_map.get(args.type.lower(), args.type)
        conditions.append(
            "(c.type_line LIKE ? AND c.type_line NOT LIKE '%//%' || ? || '%')"
        )
        params.append(f"%{card_type}%")
        params.append(card_type)

    if args.cmc is not None:
        conditions.append("c.cmc = ?")
        params.append(float(args.cmc))

    if args.mv_min is not None:
        conditions.append("c.cmc >= ?")
        params.append(float(args.mv_min))

    if args.mv_max is not None:
        conditions.append("c.cmc <= ?")
        params.append(float(args.mv_max))

    if args.color:
        color = args.color.upper()
        if args.type and args.type.lower() == "artifact":
            conditions.append(
                "(c.colors = ? OR c.colors = '[]' OR c.colors IS NULL)"
            )
            params.append(f'["{color}"]')
        else:
            conditions.append("c.colors = ?")
            params.append(f'["{color}"]')

    if args.theme:
        theme = args.theme
        conditions.append(
            "(c.oracle_text LIKE ? OR c.type_line LIKE ? OR c.name LIKE ?)"
        )
        params.extend([f"%{theme}%", f"%{theme}%", f"%{theme}%"])

    if args.owned:
        conditions.append(
            "EXISTS (SELECT 1 FROM collection col WHERE col.printing_id = p.printing_id AND col.status = 'owned')"
        )

    where = " AND ".join(conditions)

    query = f"""
        SELECT DISTINCT c.name, c.mana_cost, c.type_line, c.cmc, p.rarity,
               c.oracle_text, c.oracle_id,
               lp.price as price
        FROM cards c
        JOIN printings p ON p.oracle_id = c.oracle_id
        JOIN sets s ON s.set_code = p.set_code
        LEFT JOIN latest_prices lp ON lp.set_code = p.set_code
            AND lp.collector_number = p.collector_number
            AND lp.price_type = 'normal'
        WHERE {where}
        GROUP BY c.oracle_id
        ORDER BY c.name
    """

    if args.limit:
        query += f" LIMIT {int(args.limit)}"

    return query, params


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


def main():
    parser = argparse.ArgumentParser(
        description="Find cards matching a card shape with quality signals"
    )
    parser.add_argument("-m", "--cmc", type=int, help="Mana value (MV/CMC), exact match")
    parser.add_argument("--mv-min", type=int, help="Minimum mana value (inclusive)")
    parser.add_argument("--mv-max", type=int, help="Maximum mana value (inclusive)")
    parser.add_argument("-c", "--color", help="Color: W/U/B/R/G")
    parser.add_argument("-r", "--rarity", help="Rarity: common/uncommon/rare/mythic")
    parser.add_argument("-t", "--type", help="Card type: Creature/Instant/Sorcery/Enchantment/Artifact/Planeswalker")
    parser.add_argument("-o", "--owned", action="store_true", help="Only show cards in your collection")
    parser.add_argument("--theme", help="Theme keyword to filter by (oracle text, type line, or name)")
    parser.add_argument("--limit", type=int, default=50, help="Max results (default 50)")
    args = parser.parse_args()

    if not any([args.rarity, args.type, args.cmc is not None, args.color, args.mv_min is not None, args.mv_max is not None]):
        parser.error("Provide at least one filter (-m, -c, -r, or -t)")

    db_path = get_db_path(os.environ.get("MTGC_DB"))
    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    query, params = build_query(args)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Build filter description
    filters = []
    if args.rarity:
        filters.append(args.rarity)
    if args.color:
        color_names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        filters.append(color_names.get(args.color.upper(), args.color))
    if args.type:
        filters.append(args.type)
    if args.cmc is not None:
        filters.append(f"MV{args.cmc}")
    if args.mv_min is not None:
        filters.append(f"MV>={args.mv_min}")
    if args.mv_max is not None:
        filters.append(f"MV<={args.mv_max}")
    if args.theme:
        filters.append(f"theme:{args.theme}")
    desc = " | ".join(filters)

    print(f"Shape: {desc}")
    print(f"Found: {len(rows)} cards")
    print(f"{'=' * 70}")

    for name, mana_cost, type_line, cmc, rarity, oracle_text, oracle_id, price in rows:
        cost = mana_cost or ""
        r = rarity[0].upper() if rarity else "?"

        # Quality signals
        signals = []
        if price and price > 0:
            signals.append(f"${price:.2f}")
        effect_count, effect_list = count_effects(oracle_text)
        if effect_count >= 2:
            signals.append(f"{effect_count} effects({','.join(effect_list)})")

        signal_str = f"  [{', '.join(signals)}]" if signals else ""

        print(f"  [{r}] {cost:14s} {name:40s}{signal_str}")
        print(f"      {type_line}")
        if oracle_text:
            text = oracle_text.replace("\n", " | ")
            if len(text) > 120:
                text = text[:117] + "..."
            print(f"      {text}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
