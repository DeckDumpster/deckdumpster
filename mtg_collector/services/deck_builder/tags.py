"""Tag cards using embedding-based oracle text matching.

Embeds TAG_DESCRIPTIONS phrases, scores each card's oracle text lines
against them, and inserts tags into card_tags for lines above a cosine
similarity threshold. Keyword abilities are also mapped to tags directly.
"""

import re
import sqlite3
from typing import Callable, Dict, Optional, Set

from mtg_collector.services.deck_builder.constants import DESCRIPTION_MATCH_THRESHOLD

# Keyword abilities → tags. Applied after embedding-based tagging to catch
# vanilla/french-vanilla creatures that have no semantic oracle text to embed.
# Source: https://api.scryfall.com/catalog/keyword-abilities
KEYWORD_TAG_MAP: dict[str, str] = {
    # Evasion
    "flying": "evasion",
    "menace": "evasion",
    "shadow": "evasion",
    "skulk": "evasion",
    "horsemanship": "evasion",
    "fear": "evasion",
    "intimidate": "evasion",
    # Haste
    "haste": "gives-haste",
    # Protection / durability
    "hexproof": "gives-hexproof",
    "shroud": "gives-hexproof",
    "indestructible": "protects-creature",
    "ward": "protects-creature",
    # Combat keywords
    "first strike": "combat-trick",
    "double strike": "combat-trick",
    "deathtouch": "gives-deathtouch",
    "lifelink": "repeatable-lifegain",
    "trample": "evasion",
    "vigilance": "combat-neutral-damage-trigger",
    # Recursion / graveyard
    "unearth": "reanimate",
    "persist": "cheat-death-self",
    "undying": "cheat-death-self",
    "escape": "reanimate-cast",
    "flashback": "cast-from-nonhand",
    "retrace": "cast-from-nonhand",
    "jump-start": "cast-from-nonhand",
    "aftermath": "cast-from-nonhand",
    "disturb": "cast-from-nonhand",
    # Cost reduction / alternate casting
    "delve": "cost-reducer",
    "convoke": "cost-reducer",
    "improvise": "cost-reducer",
    "affinity": "cost-reducer",
    "evoke": "cost-reducer",
    "madness": "cast-from-nonhand",
    "foretell": "cast-from-nonhand",
    "suspend": "cast-from-nonhand",
    "cascade": "cast-from-nonhand",
    # Counters
    "modular": "gives-pp-counters",
    "fabricate": "gives-pp-counters",
    "evolve": "gives-pp-counters",
    "mentor": "gives-pp-counters",
    "training": "gives-pp-counters",
    "renown": "gives-pp-counters",
    "outlast": "gives-pp-counters",
    "graft": "gives-pp-counters",
    "reinforce": "gives-pp-counters",
    "adapt": "gives-pp-counters",
    "monstrosity": "gives-pp-counters",
    "bolster": "gives-pp-counters",
    "support": "gives-pp-counters",
    "infect": "gives-mm-counters",
    "wither": "gives-mm-counters",
    "toxic": "poison-mechanics",
    "poisonous": "poison-mechanics",
    # Tokens
    "afterlife": "repeatable-creature-tokens",
    "embalm": "repeatable-creature-tokens",
    "eternalize": "repeatable-creature-tokens",
    # Mill / self-mill
    "dredge": "self-mill",
    # Draw / selection
    "cycling": "draw",
    # Sacrifice
    "exploit": "sacrifice-outlet",
    "offering": "sacrifice-outlet",
    # Flash
    "flash": "flash",
    # Defender
    "defender": "defender",
    # Changeling (tribal)
    "changeling": "typal",
    # Ninjutsu
    "ninjutsu": "evasion",
    "commander ninjutsu": "evasion",
    # Equipment
    "living weapon": "repeatable-creature-tokens",
    "reconfigure": "gives-pp-counters",
    # Storm
    "storm": "storm",
}


def sync_tags(
    conn: sqlite3.Connection,
    progress_cb: Optional[Callable[[str], None]] = None,
    collection_only: bool = False,
) -> Dict[str, int]:
    """Tag cards by matching TAG_DESCRIPTIONS against oracle text line embeddings.

    Clears existing card_tags and rebuilds from scratch using cosine similarity
    between description phrases and per-line oracle text embeddings.

    Args:
        conn: Database connection.
        progress_cb: Optional callback for progress messages.
        collection_only: If True, only tag cards that are in the collection.

    Returns dict of tag -> count of cards tagged.
    """
    import numpy as np
    import polars as pl
    from sentence_transformers import SentenceTransformer

    from mtg_collector.services.deck_builder.tag_descriptions import TAG_DESCRIPTIONS
    from mtg_collector.utils import get_mtgc_home

    def _log(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    # Load parquet
    parquet_path = get_mtgc_home() / "line-embeddings.parquet"
    if not parquet_path.exists():
        raise ValueError(
            f"Embeddings file not found: {parquet_path}\n"
            "Run: uv run python scripts/generate_line_embeddings.py"
        )

    _log("Loading line embeddings...")
    table = pl.read_parquet(parquet_path)
    oracle_ids = table["oracle_id"].to_list()
    embeddings = np.array(table["embedding"].to_list())

    # Optionally filter to collection cards only
    collection_oids: Optional[Set[str]] = None
    if collection_only:
        collection_oids = {
            r["oracle_id"]
            for r in conn.execute(
                """SELECT DISTINCT card.oracle_id
                   FROM collection c
                   JOIN printings p ON c.printing_id = p.printing_id
                   JOIN cards card ON p.oracle_id = card.oracle_id
                   WHERE c.status = 'owned'"""
            ).fetchall()
        }
        mask = np.array([oid in collection_oids for oid in oracle_ids])
        oracle_ids = [oid for oid, m in zip(oracle_ids, mask) if m]
        embeddings = embeddings[mask]
        _log(f"Filtered to {len(oracle_ids)} lines from {len(collection_oids)} collection cards")
    else:
        _log(f"Loaded {len(oracle_ids)} lines")

    # Load model and embed description phrases
    _log("Loading embedding model...")
    model = SentenceTransformer("Alibaba-NLP/gte-modernbert-base")

    all_phrases = []
    phrase_tags = []
    for tag, phrases in TAG_DESCRIPTIONS.items():
        for phrase in phrases:
            all_phrases.append(phrase)
            phrase_tags.append(tag)

    _log(f"Encoding {len(all_phrases)} description phrases for {len(TAG_DESCRIPTIONS)} tags...")
    phrase_embeddings = model.encode(
        all_phrases, normalize_embeddings=True, show_progress_bar=False
    )

    # Score: for each tag, compute max similarity per card
    _log("Scoring cards against tag descriptions...")
    threshold = DESCRIPTION_MATCH_THRESHOLD

    # Group phrase indices by tag for efficient scoring
    tag_phrase_indices: Dict[str, list] = {}
    for i, tag in enumerate(phrase_tags):
        tag_phrase_indices.setdefault(tag, []).append(i)

    # Build per-card best score: for each (oracle_id, tag), track max similarity
    # Process one tag at a time to keep memory bounded
    tag_cards: Dict[str, set] = {}
    total_tags = len(TAG_DESCRIPTIONS)

    for tag_i, (tag, indices) in enumerate(tag_phrase_indices.items()):
        tag_embs = phrase_embeddings[indices]
        # (n_lines, n_phrases) -> max per line -> group by oracle_id
        sims = embeddings @ tag_embs.T  # embeddings already normalized from parquet
        best_per_line = sims.max(axis=1)

        # Group by oracle_id, keep max
        card_best: Dict[str, float] = {}
        for i, score in enumerate(best_per_line):
            oid = oracle_ids[i]
            if score > card_best.get(oid, -1):
                card_best[oid] = float(score)

        matched = {oid for oid, score in card_best.items() if score >= threshold}
        if matched:
            tag_cards[tag] = matched

        if (tag_i + 1) % 25 == 0:
            _log(f"  {tag_i + 1}/{total_tags} tags scored")

    # Apply keyword-based tagging
    _log("Applying keyword ability tags...")
    keyword_additions = _apply_keyword_tags(conn, tag_cards, collection_oids if collection_only else None)
    _log(f"  {keyword_additions} keyword-based tag assignments added")

    # Clear and rebuild card_tags
    _log("Writing tags to database...")
    conn.execute("DELETE FROM card_tags")

    results = {}
    for tag, oids in tag_cards.items():
        for oid in oids:
            conn.execute(
                "INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                (oid, tag),
            )
        results[tag] = len(oids)

    # Insert type-derived tags (type:creature, type:pirate, etc.)
    from mtg_collector.services.deck_builder.type_tags import insert_type_tags
    type_count = insert_type_tags(conn)
    _log(f"  + {type_count} type-derived tags")

    conn.commit()
    total_entries = sum(results.values())
    _log(f"Done: {len(results)} tags, {total_entries} tag assignments")
    return results


def _apply_keyword_tags(
    conn: sqlite3.Connection,
    tag_cards: Dict[str, set],
    collection_oids: Optional[Set[str]] = None,
) -> int:
    """Tag cards based on keyword abilities in oracle text.

    Scans oracle text for keyword abilities (flying, haste, unearth, etc.)
    and adds corresponding tags. This catches vanilla/french-vanilla creatures
    that embedding-based matching misses because keywords alone don't carry
    enough semantic signal.
    """
    # Build regex pattern: match keywords at start of line or after semicolons/newlines
    # Keywords in oracle text appear as standalone words, often with reminder text in parens
    query = (
        "SELECT oracle_id, oracle_text FROM cards "
        "WHERE oracle_text IS NOT NULL AND oracle_text != ''"
    )
    rows = conn.execute(query).fetchall()

    additions = 0
    for r in rows:
        oid = r["oracle_id"]
        if collection_oids is not None and oid not in collection_oids:
            continue

        oracle = r["oracle_text"].lower()
        # Strip reminder text in parens for cleaner matching
        oracle_clean = re.sub(r"\([^)]*\)", "", oracle)

        for keyword, tag in KEYWORD_TAG_MAP.items():
            # Match keyword at word boundary — handles "flying", "Flying",
            # "First strike", etc. whether standalone or in a list
            if re.search(r"\b" + re.escape(keyword) + r"\b", oracle_clean):
                tag_cards.setdefault(tag, set()).add(oid)
                additions += 1

    return additions
