"""Static scan: what would today's shared schema reject in a legacy collection.sqlite? (sp-63y52k)

Usage: python scripts/legacy_constraint_scan.py /path/to/collection.sqlite

Opens the legacy file read-only and immutable (it is never written, and no -wal/-shm
is created beside it), builds the target schema in an in-memory database with the
codebase's own init_db(), and for every SHARED_TABLES table (plus SHARED_VIEWS that
are tables in the legacy file) reports:

  columns    missing / extra in legacy, order differences, declared-type changes
  notnull    target NOT NULL columns that legacy rows leave NULL, matched by name and,
             where the order differs, by position (what `SELECT *` copies do)
  check      target CHECK constraints the legacy rows violate
  unique     duplicate groups for each target PRIMARY KEY / UNIQUE index
  fk         orphans for each target foreign key (only enforced with foreign_keys=ON)
  type       values whose storage class does not fit the declared affinity
             (rejected only by STRICT tables or an INTEGER PRIMARY KEY)

Every query streams through SQLite; nothing is loaded whole into Python memory.
"""

import os
import re
import sqlite3
import sys
import time

from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, init_db

EXAMPLES = 3


def q(name):
    return "[" + name + "]"


def cols(conn, schema, table):
    return [
        {"name": r[1], "type": (r[2] or "").upper(), "notnull": bool(r[3]), "dflt": r[4], "pk": r[5]}
        for r in conn.execute(f"PRAGMA {schema}.table_xinfo({q(table)})")
        if r[6] == 0  # ordinary column (not hidden / generated)
    ]


def affinity(decl):
    d = decl.upper()
    if "INT" in d:
        return "INTEGER"
    if any(s in d for s in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if d == "" or "BLOB" in d:
        return "BLOB"
    if any(s in d for s in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


# storage classes each affinity can hold after coercion without surprise
FITS = {
    "INTEGER": ("integer", "null"),
    "REAL": ("real", "integer", "null"),
    "NUMERIC": ("integer", "real", "null"),
    "TEXT": ("text", "null"),
    "BLOB": ("integer", "real", "text", "blob", "null"),
}


def check_exprs(sql):
    """Every CHECK (...) body in a CREATE TABLE statement, by paren matching."""
    out = []
    for m in re.finditer(r"\bCHECK\s*\(", sql, re.I):
        depth, i = 1, m.end()
        while depth and i < len(sql):
            depth += {"(": 1, ")": -1}.get(sql[i], 0)
            i += 1
        out.append(sql[m.end(): i - 1])
    return out


def pk_expr(conn, schema, table):
    pk = [c["name"] for c in sorted(cols(conn, schema, table), key=lambda c: c["pk"]) if c["pk"]]
    return " || '|' || ".join(f"COALESCE(CAST({q(c)} AS TEXT),'∅')" for c in pk) if pk else "rowid"


def examples(conn, table, where):
    key = pk_expr(conn, "src", table)
    return [r[0] for r in conn.execute(
        f"SELECT {key} FROM src.{q(table)} WHERE {where} LIMIT {EXAMPLES}")]


def scan_table(conn, table, out):
    findings = []

    def add(kind, msg, n=None, ex=None):
        findings.append((kind, msg, n, ex))

    exists = conn.execute(
        "SELECT type FROM src.sqlite_master WHERE name=?", (table,)).fetchone()
    if not exists:
        add("absent", "not in legacy file; nothing to copy")
        return findings
    if exists[0] != "table":
        add("absent", f"legacy object is a {exists[0]}, not a table; the copy skips it")
        return findings
    total = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)}").fetchone()[0]
    out(f"  rows: {total}")
    tgt, src = cols(conn, "main", table), cols(conn, "src", table)
    tn, sn = [c["name"] for c in tgt], [c["name"] for c in src]
    tby, sby = {c["name"]: c for c in tgt}, {c["name"]: c for c in src}
    tsql = conn.execute("SELECT sql FROM main.sqlite_master WHERE name=?", (table,)).fetchone()[0]

    # (2) columns
    for n in tn:
        if n not in sby:
            add("columns", f"{n}: missing in legacy (target default {tby[n]['dflt']!r}, notnull={tby[n]['notnull']})")
    for n in sn:
        if n not in tby:
            add("columns", f"{n}: extra in legacy (not in target; dropped by a by-name copy)")
    if [n for n in tn if n in sby] != [n for n in sn if n in tby] or len(tn) != len(sn):
        add("columns", f"order differs: target {tn} vs legacy {sn}")
    for n in tn:
        if n in sby and affinity(tby[n]["type"]) != affinity(sby[n]["type"]):
            add("columns", f"{n}: declared type {sby[n]['type']!r} -> {tby[n]['type']!r}")
    if re.search(r"\)\s*STRICT\s*;?\s*$", tsql or "", re.I):
        add("columns", "target is STRICT: type mismatches below are rejected")

    # (3) NOT NULL, by name
    for n in tn:
        c = tby[n]
        if not c["notnull"]:
            continue
        if n not in sby:
            if c["dflt"] is None and total:
                add("notnull", f"{n}: absent in legacy and no default; every row violates", total)
            continue
        k = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)} WHERE {q(n)} IS NULL").fetchone()[0]
        if k:
            add("notnull", f"{n}: NULL in legacy (target default {c['dflt']!r})", k,
                examples(conn, table, f"{q(n)} IS NULL"))
    # NOT NULL, by position (what the current `INSERT ... SELECT *` does)
    if tn != sn and len(tn) == len(sn):
        for i, c in enumerate(tgt):
            s = src[i]["name"]
            if c["name"] != s:
                add("position", f"positional copy pours legacy {s} into target {c['name']}")
            if c["notnull"] and c["name"] != s:
                k = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)} WHERE {q(s)} IS NULL").fetchone()[0]
                if k:
                    add("position", f"positional copy: {c['name']} NOT NULL <- legacy {s} NULL", k,
                        examples(conn, table, f"{q(s)} IS NULL"))

    # (4) CHECK
    for expr in check_exprs(tsql or ""):
        try:
            k = conn.execute(
                f"SELECT COUNT(*) FROM src.{q(table)} WHERE NOT ({expr})").fetchone()[0]
        except sqlite3.OperationalError as exc:
            add("check", f"CHECK ({expr}) not evaluable on legacy: {exc}")
            continue
        if k:
            add("check", f"CHECK ({expr}) violated", k, examples(conn, table, f"NOT ({expr})"))

    # (5) UNIQUE / PRIMARY KEY
    for idx in conn.execute(f"PRAGMA main.index_list({q(table)})").fetchall():
        if not idx[2]:
            continue
        icols = [r[2] for r in conn.execute(f"PRAGMA main.index_info({q(idx[1])})")]
        if any(c is None or c not in sby for c in icols):
            add("unique", f"{idx[1]} on {icols}: column(s) absent or expression; not checked")
            continue
        cl = ", ".join(q(c) for c in icols)
        nn = " AND ".join(f"{q(c)} IS NOT NULL" for c in icols)
        k = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(n),0) FROM (SELECT COUNT(*) n FROM src.{q(table)} "
            f"WHERE {nn} GROUP BY {cl} HAVING COUNT(*) > 1)").fetchone()
        if k[0]:
            joined = " || '|' || ".join(q(c) for c in icols)
            ex = [r[0] for r in conn.execute(
                f"SELECT {joined} FROM src.{q(table)} WHERE {nn} "
                f"GROUP BY {cl} HAVING COUNT(*) > 1 LIMIT {EXAMPLES}")]
            add("unique", f"{idx[3]} {icols}: {k[0]} duplicate groups", k[1], ex)
    # INTEGER PRIMARY KEY (rowid alias) has no index; a non-integer value is rejected
    for c in tgt:
        if c["pk"] and c["type"] == "INTEGER" and sum(1 for x in tgt if x["pk"]) == 1 and c["name"] in sby:
            k = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)} WHERE typeof({q(c['name'])}) != 'integer'").fetchone()[0]
            if k:
                add("unique", f"INTEGER PRIMARY KEY {c['name']} holds non-integers", k,
                    examples(conn, table, f"typeof({q(c['name'])}) != 'integer'"))

    # (6) foreign keys
    fks = {}
    for r in conn.execute(f"PRAGMA main.foreign_key_list({q(table)})"):
        fks.setdefault(r[0], {"parent": r[2], "pairs": []})["pairs"].append((r[3], r[4]))
    for fk in fks.values():
        parent = fk["parent"]
        pairs = [(f, t if t else None) for f, t in fk["pairs"]]
        if not conn.execute("SELECT 1 FROM src.sqlite_master WHERE type='table' AND name=?", (parent,)).fetchone():
            add("fk", f"{[f for f, _ in pairs]} -> {parent}: parent table absent in legacy")
            continue
        if any(t is None for _, t in pairs):
            ppk = [c["name"] for c in sorted(cols(conn, "src", parent), key=lambda c: c["pk"]) if c["pk"]]
            pairs = [(f, ppk[i]) for i, (f, _) in enumerate(pairs)]
        if any(f not in sby for f, _ in pairs):
            continue
        on = " AND ".join(f"p.{q(t)} = c.{q(f)}" for f, t in pairs)
        nn = " AND ".join(f"c.{q(f)} IS NOT NULL" for f, _ in pairs)
        where = f"{nn} AND NOT EXISTS (SELECT 1 FROM src.{q(parent)} p WHERE {on})"
        k = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)} c WHERE {where}").fetchone()[0]
        if k:
            fcols = ", ".join(f"c.{q(f)}" for f, _ in pairs)
            ex = [r[0] for r in conn.execute(
                f"SELECT DISTINCT {fcols} FROM src.{q(table)} c WHERE {where} LIMIT {EXAMPLES}")]
            add("fk", f"{[f for f, _ in pairs]} -> {parent}{[t for _, t in pairs]}: orphans "
                "(not enforced: the copy runs with foreign_keys OFF)", k, ex)

    # (7) storage class vs declared affinity
    for n in tn:
        if n not in sby:
            continue
        fits = FITS[affinity(tby[n]["type"])]
        cond = f"typeof({q(n)}) NOT IN ({', '.join(repr(f) for f in fits)})"
        k = conn.execute(f"SELECT COUNT(*) FROM src.{q(table)} WHERE {cond}").fetchone()[0]
        if k:
            kinds = [r[0] for r in conn.execute(
                f"SELECT DISTINCT typeof({q(n)}) FROM src.{q(table)} WHERE {cond}")]
            add("type", f"{n} ({tby[n]['type']}) holds {kinds} (kept as-is unless STRICT)", k,
                examples(conn, table, cond))
    return findings


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    path = os.path.abspath(argv[1])
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute("ATTACH DATABASE ? AS src", (f"file:{path}?mode=ro&immutable=1",))
    conn.execute("PRAGMA temp_store = FILE")
    ver = conn.execute("SELECT MAX(version) FROM src.schema_version").fetchone()[0]
    print(f"legacy {path}: schema_version {ver}")
    clean = []
    for table in SHARED_TABLES + SHARED_VIEWS:
        t0 = time.monotonic()
        print(f"== {table}")
        found = scan_table(conn, table, print)
        for kind, msg, n, ex in found:
            print(f"  [{kind}] {msg}" + (f" — {n} rows" if n is not None else "")
                  + (f"; e.g. {ex}" if ex else ""))
        if not found:
            clean.append(table)
            print("  clean")
        print(f"  ({time.monotonic() - t0:.1f}s)")
    print(f"\nclean: {clean}")


if __name__ == "__main__":
    main(sys.argv)
