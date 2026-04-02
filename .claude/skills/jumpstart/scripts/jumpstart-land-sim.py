#!/usr/bin/env python3
"""Simulate mana available from lands across 14 turns in Jumpstart decks.

Compares current 7/1 basic/thriving split vs proposed 6/1/1 basic/thriving/evolving split.
Outputs JSON consumed by the companion HTML visualization.

Usage:
    python jumpstart-land-sim.py [--trials 50000] [--turns 14] [--output land-sim-data.json]
"""

import argparse
import json
import random
import sys

# Card types
BASIC = "basic"
THRIVING = "thriving"
EVOLVING = "evolving"
SPELL = "spell"


def make_deck(basics, thriving, evolving):
    """Build a 40-card deck with the given land composition."""
    deck = []
    deck.extend([BASIC] * basics)
    deck.extend([THRIVING] * thriving)
    deck.extend([EVOLVING] * evolving)
    spells = 40 - len(deck)
    deck.extend([SPELL] * spells)
    return deck


def simulate_game(deck, max_turns):
    """Simulate one game, return (mana_per_turn, played_evolving).

    Mana available on turn N = number of untapped lands you control
    at the start of your main phase.

    Land play priority: basics first (untapped mana immediately),
    then thriving/evolving (enter tapped, no mana this turn).
    """
    library = deck[:]
    random.shuffle(library)

    hand = library[:7]
    library = library[7:]

    # Track lands on battlefield: list of turns they become untapped
    lands_available_turn = []

    mana_per_turn = []
    played_evolving = False

    for turn in range(1, max_turns + 1):
        if turn >= 2 and library:
            hand.append(library.pop(0))

        # Pick a land to play (if any)
        # Priority: basic (untapped) > thriving (tapped) > evolving (tapped + thins)
        land_to_play = None
        if BASIC in hand:
            land_to_play = BASIC
        elif THRIVING in hand:
            land_to_play = THRIVING
        elif EVOLVING in hand:
            land_to_play = EVOLVING

        if land_to_play:
            hand.remove(land_to_play)

            if land_to_play == BASIC:
                lands_available_turn.append(turn)
            elif land_to_play == THRIVING:
                lands_available_turn.append(turn + 1)
            elif land_to_play == EVOLVING:
                played_evolving = True
                if BASIC in library:
                    library.remove(BASIC)
                    random.shuffle(library)
                    lands_available_turn.append(turn + 1)

        mana = sum(1 for avail_turn in lands_available_turn if avail_turn <= turn)
        mana_per_turn.append(mana)

    return mana_per_turn, played_evolving


def compute_stats(per_turn_results, max_turns):
    """Compute per-turn stats from a list of per-turn mana values."""
    stats = []
    for t in range(max_turns):
        values = sorted(per_turn_results[t])
        n = len(values)
        if n == 0:
            stats.append({"turn": t + 1, "empty": True})
            continue
        stats.append({
            "turn": t + 1,
            "min": values[0],
            "q1": values[n // 4],
            "median": values[n // 2],
            "q3": values[3 * n // 4],
            "max": values[-1],
            "mean": sum(values) / n,
            "p5": values[int(n * 0.05)],
            "p95": values[int(n * 0.95)],
            "n": n,
            "distribution": _distribution(values),
        })
    return stats


def _distribution(values):
    dist = {}
    for v in values:
        dist[v] = dist.get(v, 0) + 1
    return dist


def run_scenario(name, basics, thriving, evolving, trials, max_turns, split_evolving=False):
    """Run all trials for a scenario, collect per-turn mana distributions.

    If split_evolving=True, also return sub-scenarios for games where
    EW was played vs not played.
    """
    deck = make_deck(basics, thriving, evolving)
    all_results = [[] for _ in range(max_turns)]
    ew_played_results = [[] for _ in range(max_turns)]
    ew_not_played_results = [[] for _ in range(max_turns)]

    ew_played_count = 0

    for _ in range(trials):
        mana_per_turn, played_ew = simulate_game(deck, max_turns)
        for t in range(max_turns):
            all_results[t].append(mana_per_turn[t])
        if split_evolving:
            if played_ew:
                ew_played_count += 1
                for t in range(max_turns):
                    ew_played_results[t].append(mana_per_turn[t])
            else:
                for t in range(max_turns):
                    ew_not_played_results[t].append(mana_per_turn[t])

    result = {"name": name, "stats": compute_stats(all_results, max_turns)}

    if split_evolving:
        result["ew_played"] = {
            "name": f"EW played ({ew_played_count:,} games, {ew_played_count/trials*100:.1f}%)",
            "stats": compute_stats(ew_played_results, max_turns),
        }
        result["ew_not_played"] = {
            "name": f"EW not played ({trials - ew_played_count:,} games, {(trials - ew_played_count)/trials*100:.1f}%)",
            "stats": compute_stats(ew_not_played_results, max_turns),
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="Jumpstart land mana simulation")
    parser.add_argument("--trials", type=int, default=50_000)
    parser.add_argument("--turns", type=int, default=14)
    parser.add_argument("--output", default="land-sim-data.json")
    args = parser.parse_args()

    print(f"Running {args.trials:,} trials over {args.turns} turns...", file=sys.stderr)

    # Scenario A: current — 14 basics + 2 thriving
    print("  Scenario A: 7/1 split (14 basics, 2 thriving)...", file=sys.stderr)
    scenario_a = run_scenario(
        name="Current (7 basic + 1 thriving per half)",
        basics=14, thriving=2, evolving=0,
        trials=args.trials, max_turns=args.turns,
    )

    # Scenario B: proposed — 12 basics + 2 thriving + 2 evolving
    print("  Scenario B: 6/1/1 split (12 basics, 2 thriving, 2 evolving)...", file=sys.stderr)
    scenario_b = run_scenario(
        name="Proposed (6 basic + 1 thriving + 1 evolving per half)",
        basics=12, thriving=2, evolving=2,
        trials=args.trials, max_turns=args.turns,
        split_evolving=True,
    )

    output = {
        "trials": args.trials,
        "turns": args.turns,
        "deck_size": 40,
        "scenarios": [scenario_a, scenario_b],
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  Written to {args.output}", file=sys.stderr)

    # Print summary table
    ew_info = scenario_b.get("ew_played", {})
    ew_pct = ""
    if ew_info:
        ew_pct = f" | EW played in {ew_info['name']}"
    print(f"\n  {ew_pct}", file=sys.stderr)

    print(f"\n{'Turn':<6}{'Current':>10}{'Proposed':>10}{'EW played':>12}{'EW not':>10}", file=sys.stderr)
    print("-" * 48, file=sys.stderr)
    for t in range(args.turns):
        a = scenario_a["stats"][t]["mean"]
        b = scenario_b["stats"][t]["mean"]
        ew_p = scenario_b["ew_played"]["stats"][t]["mean"] if "ew_played" in scenario_b else 0
        ew_n = scenario_b["ew_not_played"]["stats"][t]["mean"] if "ew_not_played" in scenario_b else 0
        print(f"{t+1:<6}{a:>10.2f}{b:>10.2f}{ew_p:>12.2f}{ew_n:>10.2f}", file=sys.stderr)


if __name__ == "__main__":
    main()
