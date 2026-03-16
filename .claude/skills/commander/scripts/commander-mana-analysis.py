#!/usr/bin/env python3
"""Analyze mana requirements for a commander deck to guide land base construction.

Usage: uv run python .claude/skills/commander/scripts/commander-mana-analysis.py <deck_id>

Output:
  - Colored pip counts (how many {B}, {R}, etc. across all spells)
  - Color weight percentages (what fraction of colored pips each color represents)
  - Mana curve summary
  - Recommended land count and basic land split
"""
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)

if len(argv) < 2:
    print("Usage: commander-mana-analysis.py <deck_id>")
    sys.exit(1)

deck_id = int(argv[1])

client = DeckBuilderClient(base_url)
data = client.get(f"/api/deck-builder/{deck_id}/mana-analysis")

COLOR_SYMBOLS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}

print(f"=== Mana Analysis: {data['deck_name']} ===")
print(f"Spells: {data['spell_count']}  |  Lands already in deck: {data['land_count']}")
cmd_colors = data.get("commander_colors") or []
print(f"Commander: CMC {data['commander_cmc']}, colors {'/'.join(cmd_colors) if cmd_colors else 'Colorless'}")

total_pips = data["total_colored_pips"]
print(f"\n--- Colored Pip Counts ({total_pips} total) ---")
for color in ("W", "U", "B", "R", "G"):
    pip_info = data["pip_counts"].get(color)
    if not pip_info:
        continue
    count = pip_info["count"]
    pct = pip_info["pct"]
    bar = "#" * count
    print(f"  {{{color}}} {pip_info['name']:<6} {count:>3} pips ({pct * 100:>4.0f}%)  {bar}")

print(f"\n  Generic mana: {data['generic_total']} total across all spells")

# Mana curve
avg_cmc = data["avg_cmc"]
print(f"\n--- Mana Curve (avg CMC {avg_cmc:.2f}) ---")
print(f"  {'CMC':<8} {'Yours':>5}  {'Typical':>7}  {'Delta':>6}  Chart")
for cmc in range(8):
    cmc_key = str(cmc)
    count = data["curve"].get(cmc_key, data["curve"].get(cmc, 0))
    typical = data["typical_curve"].get(cmc_key, data["typical_curve"].get(cmc, 0))
    label = f"CMC {cmc}" if cmc < 7 else "CMC 7+"
    delta = count - typical
    delta_str = f"{delta:+d}" if delta != 0 else " 0"
    bar = "#" * count
    print(f"  {label:<8} {count:>5}  {typical:>7}  {delta_str:>6}  {bar}")

# Warnings
if data.get("warnings"):
    print(f"\n  Curve warnings:")
    for w in data["warnings"]:
        print(f"    ! {w}")

# Land recommendations
print(f"\n--- Land Base Recommendation ---")
print(f"  Target:          {data['recommended_lands']} lands (Command Zone 2025 template)")
print(f"  Already in deck: {data['land_count']}")
print(f"  Need to add:     {data['lands_to_add']}")

basics = data.get("basics_split", {})
if basics:
    total_basics = sum(b["count"] for b in basics.values())
    print(f"\n--- Suggested Basic Land Split ({total_basics} basics) ---")
    for name, info in sorted(basics.items(), key=lambda x: -x[1]["count"]):
        print(f"  {name:<10} {info['count']:>2}  ({info['weight']:.0%} of colored pips)")
