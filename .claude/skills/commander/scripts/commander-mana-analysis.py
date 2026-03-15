#!/usr/bin/env python3
"""Analyze mana requirements for a commander deck to guide land base construction.

Usage: uv run python .claude/skills/commander/scripts/commander-mana-analysis.py <deck_id>

Output:
  - Colored pip counts (how many {B}, {R}, etc. across all spells)
  - Color weight percentages (what fraction of colored pips each color represents)
  - Mana curve summary
  - Recommended land count and basic land split
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path

if len(sys.argv) < 2:
    print("Usage: commander-mana-analysis.py <deck_id>")
    sys.exit(1)

deck_id = int(sys.argv[1])

conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
conn.row_factory = sqlite3.Row

# Get deck info
deck = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
if not deck:
    print(f"Deck not found: {deck_id}")
    sys.exit(1)

# Commander color identity
cmd_ci = []
if deck["commander_oracle_id"]:
    row = conn.execute(
        "SELECT color_identity FROM cards WHERE oracle_id = ?",
        (deck["commander_oracle_id"],),
    ).fetchone()
    if row and row["color_identity"]:
        cmd_ci = json.loads(row["color_identity"]) if isinstance(row["color_identity"], str) else row["color_identity"]

# Get all non-land cards in the deck
cards = conn.execute(
    """SELECT c.name, c.mana_cost, c.cmc, c.type_line
       FROM collection col
       JOIN printings p ON col.printing_id = p.printing_id
       JOIN cards c ON p.oracle_id = c.oracle_id
       WHERE col.deck_id = ?
       ORDER BY c.cmc, c.name""",
    (deck_id,),
).fetchall()

# Count ramp cards from sub_plans
ramp_count = 0
if deck["sub_plans"]:
    for cat in json.loads(deck["sub_plans"]):
        if cat["name"] == "Ramp":
            ramp_count = len(cat.get("cards", []))
            break

# --- Pip counting ---
COLOR_SYMBOLS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
pip_counts = {c: 0 for c in COLOR_SYMBOLS}
generic_total = 0
spell_count = 0
land_count = 0

# Mana curve buckets
curve = {}

for card in cards:
    type_line = (card["type_line"] or "").lower()
    is_land = "land" in type_line and "creature" not in type_line

    if is_land:
        land_count += 1
        continue

    spell_count += 1
    mana_cost = card["mana_cost"] or ""
    cmc = int(card["cmc"] or 0)
    bucket = min(cmc, 7)
    curve[bucket] = curve.get(bucket, 0) + 1

    # Parse mana symbols: {W}, {B}, {R}, {2}, {X}, {B/R}, etc.
    symbols = re.findall(r"\{([^}]+)\}", mana_cost)
    for sym in symbols:
        if sym in COLOR_SYMBOLS:
            pip_counts[sym] += 1
        elif "/" in sym:
            # Hybrid mana like {B/R} — count both colors (deck needs to cast it)
            for part in sym.split("/"):
                if part in COLOR_SYMBOLS:
                    pip_counts[part] += 1
        elif sym == "X":
            pass  # Variable, skip
        elif sym.isdigit():
            generic_total += int(sym)

# --- Commander CMC ---
cmd_cmc = 0
if deck["commander_oracle_id"]:
    row = conn.execute(
        "SELECT cmc FROM cards WHERE oracle_id = ?",
        (deck["commander_oracle_id"],),
    ).fetchone()
    if row:
        cmd_cmc = int(row["cmc"] or 0)

conn.close()

# --- Analysis ---
total_colored_pips = sum(pip_counts.values())
active_colors = {c: n for c, n in pip_counts.items() if n > 0}

# EDHREC average distribution across all decks (per ~62 non-land cards)
# Source: EDHREC "Commander Mana Curves for Beginners" + "Paradigm Shift" articles
TYPICAL_CURVE = {0: 2, 1: 8, 2: 16, 3: 15, 4: 10, 5: 6, 6: 3, 7: 2}
TYPICAL_TOTAL = sum(TYPICAL_CURVE.values())  # 62

print(f"=== Mana Analysis: {deck['name']} ===")
print(f"Spells: {spell_count}  |  Lands already in deck: {land_count}")
print(f"Commander: CMC {cmd_cmc}, colors {'/'.join(cmd_ci) if cmd_ci else 'Colorless'}")

print(f"\n--- Colored Pip Counts ({total_colored_pips} total) ---")
for color, full_name in COLOR_SYMBOLS.items():
    count = pip_counts[color]
    if count == 0 and color not in cmd_ci:
        continue
    pct = count / total_colored_pips * 100 if total_colored_pips else 0
    bar = "#" * count
    print(f"  {{{color}}} {full_name:<6} {count:>3} pips ({pct:>4.0f}%)  {bar}")

print(f"\n  Generic mana: {generic_total} total across all spells")

# --- Mana curve with comparison ---
avg_cmc = sum(cmc * count for cmc, count in curve.items()) / spell_count if spell_count else 0

print(f"\n--- Mana Curve (avg CMC {avg_cmc:.2f}) ---")
print(f"  {'CMC':<8} {'Yours':>5}  {'Typical':>7}  {'Delta':>6}  Chart")
for cmc in range(8):
    count = curve.get(cmc, 0)
    label = f"CMC {cmc}" if cmc < 7 else "CMC 7+"
    # Scale typical curve to match this deck's spell count
    typical = round(TYPICAL_CURVE.get(cmc, 0) * spell_count / TYPICAL_TOTAL)
    delta = count - typical
    delta_str = f"{delta:+d}" if delta != 0 else " 0"
    bar = "#" * count
    print(f"  {label:<8} {count:>5}  {typical:>7}  {delta_str:>6}  {bar}")

# Curve health assessment
warnings = []
if avg_cmc > 3.5:
    warnings.append("HIGH avg CMC (>3.5) — deck may be too slow, consider cutting expensive spells")
elif avg_cmc < 2.0:
    warnings.append("VERY LOW avg CMC (<2.0) — may run out of gas in longer games")

low_drops = curve.get(1, 0) + curve.get(2, 0)
if low_drops < spell_count * 0.3:
    warnings.append(f"Few 1-2 drops ({low_drops}/{spell_count}) — may struggle in early turns")

high_drops = sum(curve.get(c, 0) for c in range(6, 8))
if high_drops > spell_count * 0.15:
    warnings.append(f"Heavy top end ({high_drops} cards at CMC 6+) — ensure enough ramp to support")

if warnings:
    print(f"\n  Curve warnings:")
    for w in warnings:
        print(f"    ! {w}")

# --- Land recommendations ---
print(f"\n--- Land Base Recommendation ---")

# Base: 38 lands (Command Zone / Karsten consensus)
# Curve adjustment: +-1 for each 0.5 deviation from 3.0 avg CMC
# Ramp adjustment: -1 per 3 ramp spells (conservative — Karsten/Chimera Gaming)
base_lands = 38
curve_adj = round((avg_cmc - 3.0) * 2)  # +2 at 4.0, -2 at 2.0
curve_adj = max(-3, min(3, curve_adj))

ramp_adj = -(ramp_count // 3)  # conservative: 1 land cut per 3 ramp spells
recommended_lands = base_lands + curve_adj + ramp_adj
# Clamp to reasonable range (35 floor per community consensus)
recommended_lands = max(35, min(42, recommended_lands))

print(f"  Base target:      38 lands (Command Zone / Karsten)")
print(f"  Curve adjustment: {curve_adj:+d} (avg CMC {avg_cmc:.2f}, baseline 3.0)")
print(f"  Ramp adjustment:  {ramp_adj:+d} ({ramp_count} ramp spells, -1 per 3)")
print(f"  Recommended:      {recommended_lands} lands")
print(f"  Already in deck:  {land_count}")
print(f"  Need to add:      {max(0, recommended_lands - land_count)}")

# Basic land split based on pip ratios
if active_colors:
    nonbasic_estimate = min(land_count, recommended_lands // 3)
    basics_budget = recommended_lands - nonbasic_estimate
    print(f"\n--- Suggested Basic Land Split ({basics_budget} basics) ---")
    for color, count in sorted(active_colors.items(), key=lambda x: -x[1]):
        weight = count / total_colored_pips
        basics = round(basics_budget * weight)
        basic_name = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}[color]
        print(f"  {basic_name:<10} {basics:>2}  ({weight:.0%} of colored pips)")
