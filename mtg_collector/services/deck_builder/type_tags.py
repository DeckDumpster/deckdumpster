"""Insert type-derived tags into card_tags from cards.type_line.

Parses each card's type_line into card types (Creature, Artifact, etc.)
and subtypes (Pirate, Dragon, etc.), then inserts them as `type:X` tags
into card_tags. This lets the plan/autofill pipeline treat creature types
the same as functional tags (e.g. plan can target `type:pirate`).
"""

import sqlite3

# Supertypes to strip — these don't carry thematic deck-building meaning
_SUPERTYPES = frozenset({
    "basic", "legendary", "snow", "world", "ongoing",
    "token", "host", "elite",
})

# Card types to include as tags (lowercased for matching)
_CARD_TYPES = frozenset({
    "creature", "artifact", "enchantment", "instant", "sorcery",
    "planeswalker", "battle", "kindred",
})


def _parse_type_tags(type_line: str) -> list[str]:
    """Extract type: tags from a type_line string.

    >>> sorted(_parse_type_tags("Legendary Creature — Pirate Wizard"))
    ['type:creature', 'type:pirate', 'type:wizard']
    >>> sorted(_parse_type_tags("Artifact Creature — Robot"))
    ['type:artifact', 'type:creature', 'type:robot']
    >>> _parse_type_tags("Basic Land — Forest")
    ['type:forest']
    """
    tags = []

    # Handle DFCs: process each face
    for face in type_line.split("//"):
        face = face.strip()
        if not face:
            continue

        # Split on em dash to separate types from subtypes
        if "—" in face:
            type_part, subtype_part = face.split("—", 1)
        elif "\u2014" in face:
            type_part, subtype_part = face.split("\u2014", 1)
        else:
            type_part, subtype_part = face, ""

        # Card types (excluding supertypes)
        for word in type_part.split():
            w = word.lower().strip()
            if w in _SUPERTYPES:
                continue
            if w in _CARD_TYPES:
                tags.append(f"type:{w}")
            # Skip "Land", "Summon" etc — not useful as plan targets

        # Subtypes
        for word in subtype_part.split():
            w = word.lower().strip()
            if w:
                tags.append(f"type:{w}")

    return tags


def insert_type_tags(conn: sqlite3.Connection) -> int:
    """Insert type-derived tags into card_tags for all cards.

    Returns the number of type tag pairs inserted.
    Safe to call during migration — returns 0 if tables/columns don't exist yet.
    """
    try:
        rows = conn.execute("SELECT oracle_id, type_line FROM cards WHERE type_line IS NOT NULL").fetchall()
    except Exception:
        return 0

    count = 0
    for row in rows:
        oracle_id = row[0]
        type_line = row[1]
        tags = _parse_type_tags(type_line)
        for tag in tags:
            conn.execute(
                "INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                (oracle_id, tag),
            )
            count += 1

    conn.commit()
    return count
