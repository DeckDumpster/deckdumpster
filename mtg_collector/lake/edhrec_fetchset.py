"""The EDHREC fetch set, as a function of the catalog alone (K3).

Which commander pages get fetched used to follow the user's collection.  Landing
those pages in the shared catalog zone would then show what tenants own through
the fetch set itself, so the set is computed from `cards` and nothing else: no
`collection` row, no tenant database, is reachable from this module's inputs.
"""

import json
import re
import sqlite3

EDHREC_BASE = "https://json.edhrec.com/pages/commanders/"


def edhrec_slug(name: str) -> str:
    """Convert a card name to an EDHREC URL slug."""
    slug = name.lower()
    slug = re.sub(r"[',.]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def edhrec_url(slug: str) -> str:
    return f"{EDHREC_BASE}{slug}.json"


def commander_fetch_set(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Every legal commander in the catalog as (name, slug), sorted by name."""
    rows = conn.execute(
        """SELECT name, legalities FROM cards
           WHERE (type_line LIKE '%Legendary%' AND type_line LIKE '%Creature%')
              OR oracle_text LIKE '%can be your commander%'
           ORDER BY name"""
    ).fetchall()
    out = []
    for name, legalities in rows:
        if json.loads(legalities or "{}").get("commander") == "legal":
            out.append((name, edhrec_slug(name)))
    return out


def commander_fetch_urls(conn: sqlite3.Connection) -> list[str]:
    return [edhrec_url(slug) for _, slug in commander_fetch_set(conn)]
