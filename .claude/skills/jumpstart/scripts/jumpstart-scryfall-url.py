#!/usr/bin/env python3
"""Generate a Scryfall search URL showing all cards in a deck, using owned printings.

Usage:
    uv run python .claude/skills/jumpstart/scripts/jumpstart-scryfall-url.py "Card Name 1" "Card Name 2" ...
    uv run python .claude/skills/jumpstart/scripts/jumpstart-scryfall-url.py --open "Card 1" "Card 2" ...
"""

import sys
import urllib.parse
import urllib.request

from api_client import DeckBuilderClient, parse_host_arg


def main():
    base_url, argv = parse_host_arg(sys.argv)

    # Manual arg parsing since argparse doesn't play well with parse_host_arg
    open_browser = "--open" in argv
    card_names = [a for a in argv[1:] if a != "--open"]

    if not card_names:
        print("Usage: jumpstart-scryfall-url.py [--open] <card names...>", file=sys.stderr)
        sys.exit(1)

    client = DeckBuilderClient(base_url)
    result = client.post("/api/jumpstart/printings-by-name", {"names": card_names})

    terms = []
    for name in card_names:
        info = result.get(name)
        if not info:
            print(f"WARNING: Card not found: {name}", file=sys.stderr)
            continue
        set_code = info["set_code"]
        cn = info["collector_number"]
        terms.append(f'(!"{name}" set:{set_code.lower()})')
        print(f"  {name:30s} -> {set_code}/{cn}")

    if not terms:
        print("No cards found.", file=sys.stderr)
        sys.exit(1)

    query = " or ".join(terms)
    url = f"https://scryfall.com/search?unique=prints&q={urllib.parse.quote(query)}"

    print()
    if len(url) > 8000:
        print(f"WARNING: URL is {len(url)} chars (Scryfall limit ~8000)", file=sys.stderr)

    # Shorten via TinyURL (no auth needed)
    short_url = None
    try:
        req = urllib.request.Request(
            "https://tinyurl.com/api-create.php?" + urllib.parse.urlencode({"url": url}),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            short_url = resp.read().decode().strip()
        print(short_url)
    except Exception:
        print(url)

    if open_browser:
        import subprocess
        subprocess.run(["open", short_url or url])


if __name__ == "__main__":
    main()
