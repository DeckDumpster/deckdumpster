"""Natural ordering for names a user gave: 'Pack 2' sorts before 'Pack 10'."""

import re
from typing import Any, Dict, List

_DIGITS = re.compile(r"(\d+)")


def natural_key(name: str):
    """Digit runs compare by value, text case-insensitively.

    Parts alternate text, number, text, ... so tuples always compare like with like.
    """
    parts = _DIGITS.split((name or "").casefold())
    return [int(p) if i % 2 else p for i, p in enumerate(parts)]


def sort_by_name(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order rows by natural name, ties broken by id."""
    return sorted(rows, key=lambda r: (natural_key(r["name"]), r["id"]))
