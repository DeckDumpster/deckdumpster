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


def main():
    base_url, argv = parse_host_arg(sys.argv)

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
    args = parser.parse_args(argv[1:])

    if not any([args.rarity, args.type, args.cmc is not None, args.color, args.mv_min is not None, args.mv_max is not None]):
        parser.error("Provide at least one filter (-m, -c, -r, or -t)")

    # Build request body
    body = {}
    if args.cmc is not None:
        body["cmc"] = args.cmc
    if args.mv_min is not None:
        body["mv_min"] = args.mv_min
    if args.mv_max is not None:
        body["mv_max"] = args.mv_max
    if args.color:
        body["color"] = args.color
    if args.rarity:
        body["rarity"] = args.rarity
    if args.type:
        body["type"] = args.type
    if args.owned:
        body["owned"] = True
    if args.theme:
        body["theme"] = args.theme
    body["limit"] = args.limit

    client = DeckBuilderClient(base_url)
    rows = client.post("/api/jumpstart/find-card", body)

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

    for row in rows:
        name = row.get("name", "?")
        cost = row.get("mana_cost") or ""
        rarity = row.get("rarity") or "?"
        r = rarity[0].upper()
        oracle_text = row.get("oracle_text") or ""
        price = row.get("price")
        type_line = row.get("type_line") or ""

        signals = []
        if price and price > 0:
            signals.append(f"${price:.2f}")
        effect_count, effect_list = count_effects(oracle_text)
        if effect_count >= 2:
            signals.append(f"{effect_count} effects({','.join(effect_list)})")

        signal_str = f"  [{', '.join(signals)}]" if signals else ""

        power = row.get("power")
        toughness = row.get("toughness")
        pt_str = f"  ({power}/{toughness})" if power is not None and toughness is not None else ""

        print(f"  [{r}] {cost:14s} {name:40s}{signal_str}")
        print(f"      {type_line}{pt_str}")
        if oracle_text:
            text = oracle_text.replace("\n", " | ")
            if len(text) > 120:
                text = text[:117] + "..."
            print(f"      {text}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
