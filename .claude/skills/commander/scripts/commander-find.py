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
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from mtg_collector.db.connection import get_db_path

COLOR_ORDER = "WUBRG"


def parse_args(argv):
    args = {
        "colors": None,
        "colors_min": None,
        "colors_max": None,
        "cmc_max": None,
        "set_before": None,
        "set_after": None,
        "type": None,
        "text": None,
        "name": None,
        "sort": "name",
        "limit": 25,
    }
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
            args["colors_min"] = int(val)
        elif flag == "--colors-max":
            args["colors_max"] = int(val)
        elif flag == "--cmc-max":
            args["cmc_max"] = int(val)
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
            args["limit"] = int(val)
        else:
            print(f"Unknown flag: {flag}")
            sys.exit(1)
        i += 2
    return args


def color_sort_key(ci_json):
    """Sort color identity by number of colors, then WUBRG order."""
    colors = json.loads(ci_json) if ci_json else []
    idx = sum(1 << COLOR_ORDER.index(c) for c in colors if c in COLOR_ORDER)
    return (len(colors), idx)


def main():
    args = parse_args(sys.argv)

    conn = sqlite3.connect(get_db_path(os.environ.get("MTGC_DB")))
    conn.row_factory = sqlite3.Row

    conditions = [
        "col.status = 'owned'",
        "((c.type_line LIKE '%Legendary%' AND c.type_line LIKE '%Creature%')"
        " OR c.oracle_text LIKE '%can be your commander%')",
    ]
    params = []

    if args["colors"]:
        # Exact color identity match — build the expected JSON array
        target = sorted([c for c in args["colors"] if c in COLOR_ORDER],
                        key=lambda c: COLOR_ORDER.index(c))
        target_json = json.dumps(target)
        conditions.append("c.color_identity = ?")
        params.append(target_json)

    if args["colors_min"] is not None:
        conditions.append("json_array_length(c.color_identity) >= ?")
        params.append(args["colors_min"])

    if args["colors_max"] is not None:
        conditions.append("json_array_length(c.color_identity) <= ?")
        params.append(args["colors_max"])

    if args["cmc_max"] is not None:
        conditions.append("c.cmc <= ?")
        params.append(args["cmc_max"])

    if args["set_before"]:
        conditions.append("s.released_at < ?")
        params.append(f"{args['set_before']}-01-01")

    if args["set_after"]:
        conditions.append("s.released_at >= ?")
        params.append(f"{args['set_after']}-01-01")

    if args["type"]:
        conditions.append("c.type_line LIKE ?")
        params.append(f"%{args['type']}%")

    if args["text"]:
        conditions.append("c.oracle_text LIKE ?")
        params.append(f"%{args['text']}%")

    if args["name"]:
        conditions.append("c.name LIKE ?")
        params.append(f"%{args['name']}%")

    sort_map = {
        "name": "c.name",
        "cmc": "c.cmc, c.name",
        "set-date": "MIN(s.released_at), c.name",
        "colors": "json_array_length(c.color_identity) DESC, c.name",
    }
    order_by = sort_map.get(args["sort"], "c.name")

    where = " AND ".join(conditions)
    sql = f"""
        SELECT c.oracle_id, c.name, c.mana_cost, c.color_identity,
               c.oracle_text, c.type_line, c.cmc,
               MIN(s.released_at) AS first_printed,
               MIN(s.set_name) AS first_set,
               GROUP_CONCAT(DISTINCT s.set_name) AS all_sets,
               COUNT(DISTINCT col.id) AS copies
        FROM cards c
        JOIN printings p ON p.oracle_id = c.oracle_id
        JOIN collection col ON col.printing_id = p.printing_id
        JOIN sets s ON s.set_code = p.set_code
        WHERE {where}
        GROUP BY c.oracle_id
        ORDER BY {order_by}
        LIMIT ?
    """
    params.append(args["limit"])

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        print("No commanders found matching those filters.")
        print("\nTry broadening your search or run with --help to see options.")
        sys.exit(0)

    # Summary
    filter_desc = []
    if args["colors"]:
        filter_desc.append(f"colors={args['colors']}")
    if args["colors_min"]:
        filter_desc.append(f"{args['colors_min']}+ colors")
    if args["colors_max"]:
        filter_desc.append(f"≤{args['colors_max']} colors")
    if args["cmc_max"]:
        filter_desc.append(f"CMC ≤{args['cmc_max']}")
    if args["set_before"]:
        filter_desc.append(f"pre-{args['set_before']}")
    if args["set_after"]:
        filter_desc.append(f"post-{args['set_after']}")
    if args["type"]:
        filter_desc.append(f"type: {args['type']}")
    if args["text"]:
        filter_desc.append(f"text: {args['text']}")
    if args["name"]:
        filter_desc.append(f"name: {args['name']}")

    header = "Owned legendary creatures"
    if filter_desc:
        header += f" ({', '.join(filter_desc)})"
    print(f"{header} — {len(rows)} result(s)\n")

    for r in rows:
        ci = json.loads(r["color_identity"]) if r["color_identity"] else []
        ci_str = "".join(ci) if ci else "C"
        cmc = int(r["cmc"] or 0)

        # Truncate sets list if too long
        all_sets = r["all_sets"] or ""
        set_list = all_sets.split(",")
        if len(set_list) > 3:
            sets_display = ", ".join(set_list[:3]) + f" (+{len(set_list) - 3} more)"
        else:
            sets_display = all_sets

        print(f"  {r['name']}  [{ci_str}]  CMC {cmc}  —  {r['mana_cost']}")
        print(f"    {r['type_line']}")

        oracle = r["oracle_text"] or ""
        if oracle:
            lines = oracle.split("\n")
            for line in lines[:3]:
                if len(line) > 100:
                    line = line[:97] + "..."
                print(f"    {line}")
            if len(lines) > 3:
                print(f"    (...{len(lines) - 3} more lines)")

        print(f"    First printed: {r['first_printed'][:4] if r['first_printed'] else '?'} | Sets: {sets_display} | Copies owned: {r['copies']}")
        print()


if __name__ == "__main__":
    main()
