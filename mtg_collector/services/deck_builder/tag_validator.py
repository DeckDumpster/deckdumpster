"""Haiku-based tag validation for autofill candidates.

Scryfall tags have significant false positives. This module validates
tag assignments using Claude Haiku and caches results in the DB for
progressive improvement over time.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone

import anthropic
import httpx

# Role hints for common tags — helps Haiku understand what the tag means
TAG_ROLE_HINTS = {
    # Ramp
    "ramp": "produces extra mana or accelerates mana development",
    "mana-dork": "creature that taps for mana",
    "mana-rock": "artifact that taps for mana",
    "adds-multiple-mana": "produces 2+ mana from a single source",
    "extra-land": "lets you play additional lands per turn",
    "cost-reducer": "reduces the mana cost of spells",
    "repeatable-treasures": "creates Treasure tokens repeatedly",
    # Card advantage
    "draw": "draws cards",
    "card-advantage": "generates card advantage (draws, impulse, or creates value)",
    "tutor": "searches your library for a specific card",
    "repeatable-draw": "draws cards repeatedly (not just once)",
    "burst-draw": "draws many cards at once",
    "impulse": "exiles cards from the top of your library to cast them",
    "repeatable-impulsive-draw": "repeatedly exiles cards to cast",
    "wheel": "makes all players discard and draw new hands",
    "curiosity-like": "draws a card when a creature deals damage",
    "life-for-cards": "pays life to draw cards",
    "bottle-draw": "stores cards for later (e.g. hideaway, suspend)",
    # Targeted disruption
    "removal": "removes an opponent's permanent",
    "creature-removal": "specifically removes creatures",
    "artifact-removal": "specifically removes artifacts",
    "enchantment-removal": "specifically removes enchantments",
    "planeswalker-removal": "specifically removes planeswalkers",
    "removal-exile": "removes by exiling (not destroying)",
    "removal-toughness": "removes creatures by reducing toughness",
    "disenchant": "destroys artifacts or enchantments",
    "counter": "counters spells on the stack",
    "edict": "forces an opponent to sacrifice",
    "bounce": "returns permanents to hand",
    "graveyard-hate": "exiles or disrupts opponent graveyards",
    "land-removal": "destroys or deals with opponent lands",
    "hand-disruption": "forces opponents to discard",
    "burn-creature": "deals damage to creatures",
    # Mass disruption
    "boardwipe": "destroys or removes all creatures/permanents",
    "sweeper-one-sided": "board wipe that spares your own permanents",
    "multi-removal": "removes multiple permanents at once",
    "mass-land-denial": "destroys or locks down multiple lands",
    # Recursion / reanimation
    "recursion": "returns cards from graveyard to hand or battlefield",
    "reanimate": "puts creatures from graveyard onto the battlefield",
    # Synergy tags commonly appearing in deck plans
    "synergy-token": "creates or synergizes with creature tokens",
    "synergy-equipment": "is an equipment or synergizes with equipment",
    "synergy-counters": "uses or synergizes with +1/+1 or other counters",
    "synergy-sacrifice": "benefits from sacrificing permanents",
    "synergy-blink": "exiles and returns your own permanents for ETB triggers",
    "synergy-graveyard": "uses the graveyard as a resource",
    "synergy-lifegain": "gains life or benefits from lifegain",
    "synergy-aristocrats": "gains value from creatures dying",
    "gives-hexproof": "grants hexproof or shroud to your permanents",
    "gives-indestructible": "grants indestructible to your permanents",
    "haste-enabler": "gives creatures haste",
    "evasion": "grants or has evasion (flying, unblockable, menace, etc.)",
    "finisher": "can win the game or deal massive damage",
    "protection": "protects your permanents or life total",
}

HAIKU_MODEL = "claude-haiku-4-5-20251001"
RETRY_DELAYS = [3, 6, 12, 24]


class TagValidator:
    """Validates Scryfall tag assignments using Claude Haiku.

    Checks card_tag_validations cache first, batches unknowns to Haiku,
    stores results, and filters out invalid tags.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.client = anthropic.Anthropic(
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def validate_and_filter(self, candidates: list[dict], tag: str,
                            progress_cb=None) -> list[dict]:
        """Filter candidates by validating their tag assignment.

        For cards with no cached validations, validates ALL of the card's
        tags in one Haiku call (not just the current tag). This means
        future queries for that card against any tag are cache hits.

        1. Check card_tag_validations cache for the current tag
        2. For uncached cards, validate ALL their tags via Haiku
        3. Store all results
        4. Return only candidates valid for the current tag
        """
        if not candidates:
            return []

        oracle_ids = [c["oracle_id"] for c in candidates]

        # Look up existing validations for the current tag
        placeholders = ",".join("?" for _ in oracle_ids)
        rows = self.conn.execute(
            f"SELECT oracle_id, valid FROM card_tag_validations "  # noqa: S608
            f"WHERE tag = ? AND oracle_id IN ({placeholders})",
            [tag] + oracle_ids,
        ).fetchall()

        cached = {r["oracle_id"]: bool(r["valid"]) for r in rows}

        # Split into known-valid, known-invalid, unknown
        valid_oids = set()
        unknowns = []
        backfill = []  # Cards cached for current tag but missing other tags

        for c in candidates:
            oid = c["oracle_id"]
            if oid in cached:
                if cached[oid]:
                    valid_oids.add(oid)
                # Check if this card needs backfill (partially validated)
                validated_count = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM card_tag_validations WHERE oracle_id = ?",
                    (oid,),
                ).fetchone()["cnt"]
                total_tags = self.conn.execute(
                    "SELECT COUNT(*) AS cnt FROM card_tags WHERE oracle_id = ?",
                    (oid,),
                ).fetchone()["cnt"]
                if validated_count < total_tags:
                    backfill.append(c)
            else:
                unknowns.append(c)

        # Validate unknowns (blocks on result for current tag)
        needs_validation = unknowns + backfill
        total = len(needs_validation)
        for i in range(0, total, 5):
            batch = needs_validation[i:i + 5]
            if progress_cb:
                names = ", ".join(c["name"] for c in batch)
                progress_cb(f"Validating {names} ({i + len(batch)}/{total})")
            self._validate_all_tags_for_cards(batch)

            # Now check the cache for the current tag
            for c in batch:
                row = self.conn.execute(
                    "SELECT valid FROM card_tag_validations "
                    "WHERE oracle_id = ? AND tag = ?",
                    (c["oracle_id"], tag),
                ).fetchone()
                if row and row["valid"]:
                    valid_oids.add(c["oracle_id"])

        # Return only valid candidates, preserving original order
        return [c for c in candidates if c["oracle_id"] in valid_oids]

    def _validate_all_tags_for_cards(self, cards: list[dict]):
        """Validate ALL tags for each card in one Haiku call, caching results."""
        # Gather all tags for each card
        card_tags_map: dict[str, list[str]] = {}
        for c in cards:
            oid = c["oracle_id"]
            rows = self.conn.execute(
                "SELECT tag FROM card_tags WHERE oracle_id = ?", (oid,)
            ).fetchall()
            card_tags_map[oid] = [r["tag"] for r in rows]

        results = self._call_haiku_all_tags(cards, card_tags_map)
        now = datetime.now(timezone.utc).isoformat()

        for r in results:
            self.conn.execute(
                "INSERT OR REPLACE INTO card_tag_validations "
                "(oracle_id, tag, valid, reason, validated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (r["oracle_id"], r["tag"], int(r["valid"]), r.get("reason"), now),
            )

        self.conn.commit()

    def _call_haiku_all_tags(self, cards: list[dict],
                             card_tags_map: dict[str, list[str]]) -> list[dict]:
        """Call Claude Haiku to validate all tag assignments for a batch of cards.

        Returns list of {oracle_id, tag, valid, reason} dicts.
        """
        lines = []
        for c in cards:
            name = c.get("name", "Unknown")
            type_line = c.get("type_line", "")
            oracle_text = c.get("oracle_text", "") or ""
            tags = card_tags_map.get(c["oracle_id"], [])
            tag_hints = []
            for t in tags:
                hint = TAG_ROLE_HINTS.get(t, t.replace("-", " "))
                tag_hints.append(f"{t} ({hint})")
            lines.append(
                f"- **{name}** ({type_line}): \"{oracle_text}\"\n"
                f"  Tags: {', '.join(tag_hints)}"
            )

        card_block = "\n".join(lines)

        prompt = f"""For each card below, determine which of its assigned tags are genuinely correct and which are false positives.

A tag is VALID if the card actually fulfills that role. A tag is INVALID if it's a misleading association (e.g. a card tagged "mana-rock" that doesn't produce mana, or "creature-removal" on a card that can't remove creatures).

Cards and their tags:
{card_block}

For each card, evaluate ALL its tags. Respond with a JSON array where each element is:
{{"name": "Card Name", "tag": "tag-name", "valid": true/false, "reason": "brief explanation"}}

Return ONLY the JSON array, no other text."""

        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = self.client.messages.create(
                    model=HAIKU_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text.strip()
                # Strip markdown code fences if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:-3].strip()

                results = json.loads(text)

                # Map results back to oracle_ids
                name_to_oid = {c["name"]: c["oracle_id"] for c in cards}
                validated = []
                responded_keys: set[tuple[str, str]] = set()

                for r in results:
                    oid = name_to_oid.get(r.get("name"))
                    tag = r.get("tag")
                    if oid and tag:
                        validated.append({
                            "oracle_id": oid,
                            "tag": tag,
                            "valid": bool(r.get("valid", False)),
                            "reason": r.get("reason", ""),
                        })
                        responded_keys.add((oid, tag))

                # Any tags not in response — assume valid (don't block)
                for c in cards:
                    oid = c["oracle_id"]
                    for tag in card_tags_map.get(oid, []):
                        if (oid, tag) not in responded_keys:
                            validated.append({
                                "oracle_id": oid,
                                "tag": tag,
                                "valid": True,
                                "reason": "not in Haiku response, assumed valid",
                            })

                return validated

            except anthropic.BadRequestError:
                # Don't retry 400 errors
                break
            except (anthropic.APIError, json.JSONDecodeError):
                if attempt < len(RETRY_DELAYS):
                    time.sleep(RETRY_DELAYS[attempt])
                else:
                    break

        # On total failure, assume all valid (don't block autofill)
        all_results = []
        for c in cards:
            oid = c["oracle_id"]
            for tag in card_tags_map.get(oid, []):
                all_results.append({
                    "oracle_id": oid,
                    "tag": tag,
                    "valid": True,
                    "reason": "validation failed, assumed valid",
                })
        return all_results
