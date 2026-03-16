#!/usr/bin/env python3
"""Browse owned legendary creatures for commander selection.

Usage:
  commander-find.py [options]

Options:
  --colors COLORS     Filter by color identity (e.g. WUB, RG, WUBRG). Exact match.
  --colors-min N      Minimum number of colors (e.g. 2 for multicolor)
  --colors-max N      Maximum number of colors
  --cmc-max N         Maximum mana value
  --set-before YEAR   Only cards from sets released before this year (e.g. 2015)
  --set-after YEAR    Only cards from sets released after this year
  --type TEXT         Additional type filter (e.g. "Dragon", "Elf", "God")
  --text TEXT         Search oracle text (e.g. "sacrifice", "counter", "token")
  --name TEXT         Filter by name substring
  --sort FIELD        Sort by: name (default), cmc, set-date, colors
  --limit N           Max results (default 25)

Examples:
  commander-find.py --colors-min 3 --set-before 2015
  commander-find.py --colors RG --type Dragon
  commander-find.py --text "whenever a creature dies" --colors-min 2
  commander-find.py --set-before 2010 --sort set-date
  commander-find.py --colors WUB --cmc-max 4
"""
import json
import sys

from api_client import DeckBuilderClient, parse_host_arg

base_url, argv = parse_host_arg(sys.argv)


def parse_args(argv):
    args = {}
    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        if i + 1 >= len(argv):
            print(f"Missing value for {flag}")
            sys.exit(1)
        val = argv[i + 1]
        if flag == "--colors":
            args["colors"] = val.upper()
        elif flag == "--colors-min":
            args["colors_min"] = val
        elif flag == "--colors-max":
            args["colors_max"] = val
        elif flag == "--cmc-max":
            args["cmc_max"] = val
        elif flag == "--set-before":
            args["set_before"] = val
        elif flag == "--set-after":
            args["set_after"] = val
        elif flag == "--type":
            args["type"] = val
        elif flag == "--text":
            args["text"] = val
        elif flag == "--name":
            args["name"] = val
        elif flag == "--sort":
            args["sort"] = val
        elif flag == "--limit":
            args["limit"] = val
        else:
            print(f"Unknown flag: {flag}")
            sys.exit(1)
        i += 2
    return args


args = parse_args(argv)

client = DeckBuilderClient(base_url)
# Convert args dict to query params (only non-empty values)
params = {k: v for k, v in args.items() if v}
rows = client.get("/api/deck-builder/commanders/browse", params)

if not rows:
    print("No commanders found matching those filters.")
    print("\nTry broadening your search or run with --help to see options.")
    sys.exit(0)

# Summary
filter_desc = []
if args.get("colors"):
    filter_desc.append(f"colors={args['colors']}")
if args.get("colors_min"):
    filter_desc.append(f"{args['colors_min']}+ colors")
if args.get("colors_max"):
    filter_desc.append(f"≤{args['colors_max']} colors")
if args.get("cmc_max"):
    filter_desc.append(f"CMC ≤{args['cmc_max']}")
if args.get("set_before"):
    filter_desc.append(f"pre-{args['set_before']}")
if args.get("set_after"):
    filter_desc.append(f"post-{args['set_after']}")
if args.get("type"):
    filter_desc.append(f"type: {args['type']}")
if args.get("text"):
    filter_desc.append(f"text: {args['text']}")
if args.get("name"):
    filter_desc.append(f"name: {args['name']}")

header = "Owned legendary creatures"
if filter_desc:
    header += f" ({', '.join(filter_desc)})"
print(f"{header} — {len(rows)} result(s)\n")

for r in rows:
    ci = json.loads(r["color_identity"]) if isinstance(r.get("color_identity"), str) else (r.get("color_identity") or [])
    ci_str = "".join(ci) if ci else "C"
    cmc = int(r.get("cmc") or 0)

    # Truncate sets list if too long
    all_sets = r.get("all_sets") or ""
    set_list = all_sets.split(",") if all_sets else []
    if len(set_list) > 3:
        sets_display = ", ".join(set_list[:3]) + f" (+{len(set_list) - 3} more)"
    else:
        sets_display = all_sets

    print(f"  {r['name']}  [{ci_str}]  CMC {cmc}  —  {r.get('mana_cost', '')}")
    print(f"    {r.get('type_line', '')}")

    oracle = r.get("oracle_text") or ""
    if oracle:
        lines = oracle.split("\n")
        for line in lines[:3]:
            if len(line) > 100:
                line = line[:97] + "..."
            print(f"    {line}")
        if len(lines) > 3:
            print(f"    (...{len(lines) - 3} more lines)")

    first_printed = r.get("first_printed") or ""
    print(f"    First printed: {first_printed[:4] if first_printed else '?'} | Sets: {sets_display} | Copies owned: {r.get('copies', '?')}")
    print()
