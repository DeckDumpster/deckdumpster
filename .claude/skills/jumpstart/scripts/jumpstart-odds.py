#!/usr/bin/env python3
"""Calculate probability of drawing card combinations in a Jumpstart game.

Uses Monte Carlo simulation (200k trials) over a 40-card deck.

Usage:
    # Combo check: need Dark Ritual + Gwenom + a land in opening hand
    jumpstart-odds.py 1 1 16 --by 8 --label "Dark Ritual" "Gwenom" "lands"

    # Density check: need 5 goblins in first 20 cards from pool of 9
    jumpstart-odds.py 9 --need 5 --by 20 --label "goblins"
"""

import argparse
import random
import sys

TRIALS = 200_000


def simulate(group_sizes, needs, draw_count, deck_size):
    """Run Monte Carlo simulation and return success count."""
    # Build deck as list of group indices; -1 = filler
    deck = []
    for i, size in enumerate(group_sizes):
        deck.extend([i] * size)
    deck.extend([-1] * (deck_size - len(deck)))

    successes = 0
    for _ in range(TRIALS):
        hand = random.sample(deck, draw_count)
        counts = [0] * len(group_sizes)
        for card in hand:
            if card >= 0:
                counts[card] += 1
        if all(counts[i] >= needs[i] for i in range(len(group_sizes))):
            successes += 1
    return successes


def main():
    parser = argparse.ArgumentParser(
        description="Calculate probability of drawing card combinations in a Jumpstart game."
    )
    parser.add_argument(
        "groups", nargs="+", type=int,
        help="Size of each card group in the deck (e.g., 1 1 16)"
    )
    parser.add_argument(
        "--need", nargs="+", type=int, default=None,
        help="How many needed from each group (default: 1 each)"
    )
    parser.add_argument(
        "--by", type=int, default=8, dest="draw_count",
        help="Cards drawn (default: 8 = opening hand + first draw)"
    )
    parser.add_argument(
        "--deck", type=int, default=40,
        help="Deck size (default: 40)"
    )
    parser.add_argument(
        "--label", nargs="+", default=None,
        help="Optional names for each group"
    )
    args = parser.parse_args()

    group_sizes = args.groups
    needs = args.need if args.need else [1] * len(group_sizes)
    labels = args.label if args.label else [None] * len(group_sizes)

    # Validation
    if len(needs) != len(group_sizes):
        print(f"Error: --need has {len(needs)} values but {len(group_sizes)} groups given", file=sys.stderr)
        return 1
    if len(labels) < len(group_sizes):
        labels.extend([None] * (len(group_sizes) - len(labels)))
    total_grouped = sum(group_sizes)
    if total_grouped > args.deck:
        print(f"Error: group sizes sum to {total_grouped}, exceeds deck size {args.deck}", file=sys.stderr)
        return 1
    if args.draw_count > args.deck:
        print(f"Error: can't draw {args.draw_count} from a {args.deck}-card deck", file=sys.stderr)
        return 1
    for i, (size, need) in enumerate(zip(group_sizes, needs)):
        if need > size:
            name = labels[i] or f"group {i + 1}"
            print(f"Error: need {need} from {name} but only {size} in deck", file=sys.stderr)
            return 1

    # Run simulation
    successes = simulate(group_sizes, needs, args.draw_count, args.deck)
    probability = successes / TRIALS * 100

    # Output
    print(f"Deck: {args.deck} cards | Drawing: {args.draw_count} cards")
    print()
    for i, (size, need) in enumerate(zip(group_sizes, needs)):
        label_str = f"  ({labels[i]})" if labels[i] else ""
        card_word = "card" if size == 1 else "cards"
        need_str = f"{need}" if need > 1 else "1"
        print(f"  Group {i + 1}: {need_str} of {size} {card_word}{label_str}")
    print()
    print(f"  Probability: {probability:.1f}%")
    print()
    print(f"  ({TRIALS:,} simulations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
