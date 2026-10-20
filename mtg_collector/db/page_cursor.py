"""Keyset cursors for paged result sets.

LIMIT/OFFSET makes a deep window re-execute the query and throw away every
earlier row: one window at offset=50000 of an is:unowned result took 2251 ms
on 110,018 printings. A cursor instead names the last row the caller saw, and
the next window seeks past it.

The token is opaque to callers. It carries the sort key of the last row (every
ORDER BY term, the unique tie-break included), the whole-result total, and a
fingerprint of the query that produced it, so a token replayed against another
query or sort is refused rather than silently seeking into the wrong order.
"""

from __future__ import annotations

import base64
import hashlib
import json

_VERSION = 1


class CursorError(ValueError):
    """A cursor the caller must fix. Surfaced as a 400."""


def fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def encode(fp: str, key: list, total: int) -> str:
    raw = json.dumps({"v": _VERSION, "f": fp, "k": key, "t": total}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode(token: str, fp: str, width: int) -> tuple[list, int]:
    """Return (key values, total), or raise CursorError."""
    try:
        padded = token + "=" * (-len(token) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode()))
        key, total = body["k"], body["t"]
        version, token_fp = body["v"], body["f"]
    except (ValueError, KeyError, TypeError):
        raise CursorError("cursor is not valid") from None
    if version != _VERSION:
        raise CursorError("cursor is from an incompatible version")
    if token_fp != fp:
        raise CursorError(
            "cursor was issued for a different query or sort; "
            "start again without a cursor"
        )
    if not isinstance(key, list) or len(key) != width or not isinstance(total, int):
        raise CursorError("cursor is not valid")
    return key, total


def seek(exprs: list[str], values: list, desc: bool) -> tuple[str, list]:
    """SQL (and params) selecting the rows strictly after `values`.

    `exprs` are the ORDER BY terms, all in one direction. SQLite orders NULL
    before every value, and a row-value comparison against NULL is NULL, so
    the lexicographic expansion is written out with IS / IS NOT NULL.

    The first term also gets a plain `>=` / `<=` bound: the expansion is an
    OR chain the planner will not turn into an index range on its own, and
    the bound is what lets an index on the leading term start at the cursor
    instead of at the top. Descending, NULLs sort last, so the bound admits them.
    """
    clauses: list[str] = []
    params: list = []
    for i, (expr, value) in enumerate(zip(exprs, values)):
        parts: list[str] = []
        p: list = []
        for e, v in zip(exprs[:i], values[:i]):
            parts.append(f"{e} IS ?")
            p.append(v)
        if desc:
            if value is None:
                continue
            parts.append(f"({expr} < ? OR {expr} IS NULL)")
            p.append(value)
        elif value is None:
            parts.append(f"{expr} IS NOT NULL")
        else:
            parts.append(f"{expr} > ?")
            p.append(value)
        clauses.append("(" + " AND ".join(parts) + ")")
        params.extend(p)
    sql = "(" + " OR ".join(clauses) + ")" if clauses else "0"
    if values[0] is not None:
        bound = f"({exprs[0]} <= ? OR {exprs[0]} IS NULL)" if desc else f"{exprs[0]} >= ?"
        sql = f"{bound} AND {sql}"
        params.insert(0, values[0])
    return sql, params
