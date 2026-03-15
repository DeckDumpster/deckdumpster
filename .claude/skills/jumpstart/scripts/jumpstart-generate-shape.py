#!/usr/bin/env python3
"""Generate a soft Jumpstart 2025 pack shape: curve + creature count + rarity budget.

Unlike a rigid per-slot shape, this outputs aggregate targets that guide
theme-first deck building.

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-generate-shape.py G
    uv run python .claude/skills/jumpstart/scripts/jumpstart-generate-shape.py W --rare-category bomb
    uv run python .claude/skills/jumpstart/scripts/jumpstart-generate-shape.py --seed 42 B --rare-category engine
"""

import argparse
import random
import sys

# Observed distributions from J25 analysis (weights for random selection)

# 8 lands: 112 decks, 9 lands: 9 decks (excluding Chaos)
LAND_COUNT_WEIGHTS = {8: 112, 9: 9}

# Creature count distribution (for 12-nonland / 11-nonland decks)
CREATURE_COUNT_12 = {8: 76, 7: 25, 6: 9, 5: 2}
CREATURE_COUNT_11 = {7: 8, 8: 1}  # 9-land decks

# Rare/mythic count among non-lands
RM_COUNT_WEIGHTS = {1: 81, 2: 40}

# Uncommon count among non-lands (for 12-nonland decks, most common combos)
U_COUNT_WEIGHTS = {4: 99, 5: 10, 3: 12}

# MV distributions (observed counts across 121 decks, used as weights)
MV_WEIGHTS = {
    1: {0: 18, 1: 36, 2: 49, 3: 16, 4: 2},
    2: {1: 3, 2: 13, 3: 50, 4: 30, 5: 21, 6: 4},
    3: {1: 1, 2: 26, 3: 47, 4: 38, 5: 9},
    4: {0: 2, 1: 43, 2: 55, 3: 19, 4: 2},
    5: {0: 29, 1: 62, 2: 27, 3: 3},
    6: {0: 68, 1: 46, 2: 7},
    7: {0: 96, 1: 19, 2: 6},
}

RARE_CATEGORIES = {
    "bomb": "MV 4+ finisher — deck ramps into it",
    "engine": "Repeated value — triggers, activated abilities, recursion",
    "lord": "MV 1-3 enabler — tribal lord, anthem, cost reducer",
}

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


def weighted_choice(weights_dict):
    """Pick a key from {value: weight} dict."""
    keys = list(weights_dict.keys())
    weights = [weights_dict[k] for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]


def generate_mana_curve(nonland_count):
    """Generate a valid mana curve that sums to nonland_count."""
    for _ in range(1000):
        curve = {}
        curve[0] = 0
        for mv in range(1, 8):
            curve[mv] = weighted_choice(MV_WEIGHTS[mv])

        total = sum(curve.values())
        if total != nonland_count:
            continue

        # Validate constraints
        if curve[2] < 1 or curve[3] < 1:
            continue
        mv23 = curve[2] + curve[3]
        if mv23 < 4 or mv23 > 10:
            continue
        mv5plus = curve[5] + curve[6] + curve[7]
        if mv5plus > 4:
            continue

        return curve

    raise RuntimeError("Failed to generate valid mana curve after 1000 attempts")


def generate_pack(color):
    """Generate a J25 soft pack shape: aggregate targets, not per-slot assignments."""
    land_count = weighted_choice(LAND_COUNT_WEIGHTS)
    nonland_count = 20 - land_count

    if nonland_count == 12:
        creature_count = weighted_choice(CREATURE_COUNT_12)
    else:
        creature_count = weighted_choice(CREATURE_COUNT_11)
    spell_count = nonland_count - creature_count

    rm_count = weighted_choice(RM_COUNT_WEIGHTS)
    u_count = weighted_choice(U_COUNT_WEIGHTS)
    c_count = nonland_count - rm_count - u_count

    if c_count < 5:
        u_count = nonland_count - rm_count - 5
        c_count = 5
    if c_count > 8:
        u_count = nonland_count - rm_count - 8
        c_count = 8

    curve = generate_mana_curve(nonland_count)

    # Land breakdown
    has_extra_nonbasic = random.random() < 0.25
    basic_count = land_count - 1 - (1 if has_extra_nonbasic else 0)

    return {
        "nonland_count": nonland_count,
        "creature_count": creature_count,
        "spell_count": spell_count,
        "rm_count": rm_count,
        "u_count": u_count,
        "c_count": c_count,
        "curve": curve,
        "land_count": land_count,
        "basic_count": basic_count,
        "has_extra_nonbasic": has_extra_nonbasic,
        "color": color,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a J25 soft pack shape")
    parser.add_argument("color", nargs="?", choices=["W", "U", "B", "R", "G"],
                        help="Color (W/U/B/R/G). Random if omitted.")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument("--rare-category", choices=["bomb", "engine", "lord"],
                        help="Rare card category: bomb/engine/lord")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    color = args.color or random.choice(["W", "U", "B", "R", "G"])
    pack = generate_pack(color)

    print(f"J25 Soft Shape — {COLOR_NAMES[color]}")
    print(f"{'=' * 50}")

    if args.rare_category:
        print(f"Rare category: {args.rare_category} ({RARE_CATEGORIES[args.rare_category]})")
    print()

    print(f"Rarity budget: {pack['rm_count']} R/M, {pack['u_count']} U, {pack['c_count']} C")
    print(f"Creatures: {pack['creature_count']}    Non-creature spells: {pack['spell_count']}")
    print()

    print("Curve targets:")
    curve_parts = []
    for mv in range(1, 8):
        count = pack["curve"].get(mv, 0)
        if count > 0:
            curve_parts.append(f"  MV{mv}: {count}")
    print("  " + "    ".join(curve_parts))
    print(f"  ({pack['nonland_count']} spells total)")
    print()

    print("Lands:")
    if pack["has_extra_nonbasic"]:
        print("  1 nonbasic land (your choice)")
    print(f"  1 {THRIVING_NAMES[color]}")
    print(f"  {pack['basic_count']} {BASIC_NAMES[color]}")
    print()

    print(f"Search: use -c {color} -r <rarity> -o --theme <keyword>")
    if args.rare_category == "bomb":
        print(f"Identity card: search -c {color} -r rare --mv-min 4 -o --theme <keyword>")
    elif args.rare_category == "lord":
        print(f"Identity card: search -c {color} -r rare --mv-max 3 -o --theme <keyword>")
    else:
        print(f"Identity card: search -c {color} -r rare -o --theme <keyword>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
