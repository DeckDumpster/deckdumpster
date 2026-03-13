"""Haiku-based tag validation for autofill candidates.

Scryfall tags have significant false positives. This module validates
tag assignments using Claude Haiku and caches results in the DB for
progressive improvement over time.

Each validation call is ONE card with only the tags relevant to the
current deck plan (intersected with the card's tags, minus already-cached).
Structured output guarantees valid JSON — no parsing errors.
"""

import sqlite3
from datetime import datetime, timezone

import anthropic
import httpx
from pydantic import BaseModel

from mtg_collector.services.retry import anthropic_retry

# Hints only for tags where Haiku would plausibly get it wrong.
# Most tags are self-evident from their name.
TAG_ROLE_HINTS = {
    "ramp": "must NET INCREASE mana sources — fetchlands are NOT ramp",
    "boardwipe": "can potentialy destory 5 or more creatures given the right board state",
    "multi-removal": "removes 2+ permanents in one action, not single-target",
    "card-advantage": "must generate net card advantage, not just filter/loot",
    "mana-rock": "an artifact that generates mana",
    "mana-dork": "a creature that generates mana"
}

HAIKU_MODEL = "claude-haiku-4-5-20251001"


class TagResult(BaseModel):
    tag: str
    valid: bool


class TagValidation(BaseModel):
    results: list[TagResult]


class TagValidator:
    """Validates Scryfall tag assignments using Claude Haiku.

    Checks card_tag_validations cache first, calls Haiku for unknowns
    one card at a time, stores results, and filters out invalid tags.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.client = anthropic.Anthropic(
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def validate_and_filter(self, candidates: list[dict], tag: str,
                            progress_cb=None) -> list[dict]:
        """Filter candidates by validating their tag assignment.

        1. Check card_tag_validations cache for the current tag
        2. For uncached cards, validate relevant tags via Haiku (one card at a time)
        3. Store results
        4. Return only candidates valid for the current tag
        """
        if not candidates:
            return []

        # Type tags are deterministically correct — no Haiku needed.
        if tag.startswith("type:"):
            return self._validate_type_tag(candidates, tag)

        oracle_ids = [c["oracle_id"] for c in candidates]

        # Look up existing validations for the current tag
        placeholders = ",".join("?" for _ in oracle_ids)
        rows = self.conn.execute(
            f"SELECT oracle_id, valid FROM card_tag_validations "  # noqa: S608
            f"WHERE tag = ? AND oracle_id IN ({placeholders})",
            [tag] + oracle_ids,
        ).fetchall()

        cached = {r["oracle_id"]: bool(r["valid"]) for r in rows}

        valid_oids = set()
        unknowns = []

        for c in candidates:
            oid = c["oracle_id"]
            if oid in cached:
                if cached[oid]:
                    valid_oids.add(oid)
            else:
                unknowns.append(c)

        # Validate one card at a time
        for c in unknowns:
            if progress_cb:
                progress_cb(f"Validating tags for {c['name']}")
            self._validate_card(c)

            row = self.conn.execute(
                "SELECT valid FROM card_tag_validations "
                "WHERE oracle_id = ? AND tag = ?",
                (c["oracle_id"], tag),
            ).fetchone()
            if row and row["valid"]:
                valid_oids.add(c["oracle_id"])

        return [c for c in candidates if c["oracle_id"] in valid_oids]

    def _validate_type_tag(self, candidates: list[dict], tag: str) -> list[dict]:
        """Validate a type: tag deterministically from type_line."""
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags

        now = datetime.now(timezone.utc).isoformat()
        valid = []
        for c in candidates:
            oid = c["oracle_id"]
            type_line = c.get("type_line") or ""
            card_type_tags = _parse_type_tags(type_line)
            is_valid = tag in card_type_tags

            self.conn.execute(
                "INSERT OR IGNORE INTO card_tag_validations "
                "(oracle_id, tag, valid, reason, validated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (oid, tag, int(is_valid), "type_line check", now),
            )

            if is_valid:
                valid.append(c)

        self.conn.commit()
        return valid

    def _validate_card(self, card: dict):
        """Validate one card's unvalidated tags via Haiku, cache results."""
        oid = card["oracle_id"]

        # Get all non-type tags for this card
        rows = self.conn.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = ?", (oid,)
        ).fetchall()
        all_tags = [r["tag"] for r in rows if not r["tag"].startswith("type:")]

        # Subtract already-cached validations
        cached_rows = self.conn.execute(
            "SELECT tag FROM card_tag_validations WHERE oracle_id = ?", (oid,)
        ).fetchall()
        cached_tags = {r["tag"] for r in cached_rows}
        tags_to_validate = [t for t in all_tags if t not in cached_tags]

        if not tags_to_validate:
            return

        # Build minimal prompt
        name = card.get("name", "Unknown")
        type_line = card.get("type_line", "")
        oracle_text = card.get("oracle_text", "") or ""

        # Only include hints for tags being validated
        hints = []
        for t in tags_to_validate:
            if t in TAG_ROLE_HINTS:
                hints.append(f"- {t}: {TAG_ROLE_HINTS[t]}")

        hint_block = ""
        if hints:
            hint_block = "\n\nNotes:\n" + "\n".join(hints)

        prompt = (
            f"Does this card fulfill these roles?\n\n"
            f"{name} ({type_line}): \"{oracle_text}\"\n"
            f"Tags: {', '.join(tags_to_validate)}"
            f"{hint_block}"
        )

        response = anthropic_retry(lambda: self.client.messages.parse(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_format=TagValidation,
        ))

        now = datetime.now(timezone.utc).isoformat()
        for r in response.parsed_output.results:
            if r.tag in tags_to_validate:
                self.conn.execute(
                    "INSERT OR REPLACE INTO card_tag_validations "
                    "(oracle_id, tag, valid, reason, validated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (oid, r.tag, int(r.valid), None, now),
                )

        self.conn.commit()
