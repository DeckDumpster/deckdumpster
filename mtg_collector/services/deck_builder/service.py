"""Deck builder service for Commander/EDH deck construction."""

import json
import sqlite3
from typing import List, Optional, Set

from mtg_collector.db.models import (
    CardRepository,
    CollectionRepository,
    Deck,
    DeckRepository,
    PrintingRepository,
)
from mtg_collector.services.deck_builder.constants import (
    ANY_NUMBER_CARDS,
    AVG_CMC_TARGET,
    BASIC_LANDS,
    BLING_WEIGHTS,
    CREATURE_CURVE_TARGETS,
    DECK_SIZE,
    DEFAULT_FORMAT,
    INFRASTRUCTURE,
    LAND_COUNTS,
    LAND_TARGET_DEFAULT,
    NONCREATURE_CURVE_TARGETS,
    SNOW_BASICS,
    ZONE_COMMANDER,
    ZONE_MAINBOARD,
)
from mtg_collector.utils import parse_json_array


class DeckBuilderService:
    """Service for building Commander/EDH decks from owned cards."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.card_repo = CardRepository(conn)
        self.printing_repo = PrintingRepository(conn)
        self.collection_repo = CollectionRepository(conn)
        self.deck_repo = DeckRepository(conn)

    # ── Deck lifecycle ──────────────────────────────────────────────

    def create_deck(self, commander_name: str) -> dict:
        """Create a new Commander deck with the given commander."""
        card = self._resolve_card(commander_name)

        # Validate it's a legal commander
        self._validate_commander(card.oracle_id, card.name, card.type_line)

        # Create deck
        deck = Deck(id=None, name=card.name, format=DEFAULT_FORMAT)
        deck_id = self.deck_repo.add(deck)

        # Find best owned copy and assign as commander
        copy_id = self._find_best_copy(card.oracle_id, deck_id)
        if copy_id:
            self.deck_repo.add_cards(deck_id, [copy_id], zone=ZONE_COMMANDER)

        self.conn.commit()
        return {"deck_id": deck_id, "commander": card.name, "copy_assigned": copy_id is not None}

    def delete_deck(self, deck_id: int) -> dict:
        """Delete a deck, unassigning all cards."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")
        name = deck["name"]
        self.deck_repo.delete(deck_id)
        self.conn.commit()
        return {"deck_id": deck_id, "name": name}

    def describe_deck(self, deck_id: int, description: str) -> dict:
        """Set the deck description."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")
        self.deck_repo.update(deck_id, {"description": description})
        self.conn.commit()
        return {"deck_id": deck_id, "description": description}

    # ── Card management ─────────────────────────────────────────────

    def add_card(self, deck_id: int, card_name: str, zone: str = ZONE_MAINBOARD,
                 note: Optional[str] = None, count: int = 1) -> dict:
        """Add a card to the deck."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        card = self._resolve_card(card_name)

        # Check color identity
        commander_ci = self._get_commander_identity(deck_id)
        if commander_ci is not None:
            card_ci = set(card.color_identity)
            if not card_ci.issubset(commander_ci):
                raise ValueError(
                    f"'{card.name}' color identity {card_ci} is not a subset of commander identity {commander_ci}"
                )

        # Check singleton rule
        if not self._is_basic_land(card.name) and not self._is_any_number(card.name, card.oracle_text):
            existing = self._cards_in_deck_by_name(deck_id, card.name)
            if existing:
                raise ValueError(f"'{card.name}' is already in the deck (singleton rule)")

        added = []
        for _ in range(count):
            copy_id = self._find_best_copy(card.oracle_id, deck_id)
            if not copy_id:
                raise ValueError(self._explain_no_copy(card.name, card.oracle_id))
            self.deck_repo.add_cards(deck_id, [copy_id], zone=zone)
            if note:
                self.conn.execute(
                    "UPDATE collection SET deck_note = ? WHERE id = ?",
                    (note, copy_id),
                )
            added.append(copy_id)

        self.conn.commit()
        tally = self._get_deck_tally(deck_id)
        return {"card": card.name, "zone": zone, "count": len(added),
                "collection_ids": added, "tally": tally}

    def remove_card(self, deck_id: int, card_name: str, count: int = 1) -> dict:
        """Remove a card from the deck by name."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        matches = self._cards_in_deck_by_name(deck_id, card_name)
        if not matches:
            raise ValueError(f"'{card_name}' not found in deck {deck_id}")

        to_remove = [m["id"] for m in matches[:count]]
        self.deck_repo.remove_cards(deck_id, to_remove)
        self.conn.commit()
        tally = self._get_deck_tally(deck_id)
        return {"card": card_name, "removed": len(to_remove), "tally": tally}

    def swap_card(self, deck_id: int, out_name: str, in_name: str,
                  note: Optional[str] = None) -> dict:
        """Swap one card for another in the deck."""
        out_result = self.remove_card(deck_id, out_name, count=1)
        in_result = self.add_card(deck_id, in_name, note=note)
        return {"removed": out_result["card"], "added": in_result["card"]}

    def annotate_card(self, deck_id: int, card_name: str,
                      note: Optional[str] = None) -> dict:
        """Update the note on a card in the deck."""
        matches = self._cards_in_deck_by_name(deck_id, card_name)
        if not matches:
            raise ValueError(f"'{card_name}' not found in deck {deck_id}")

        cid = matches[0]["id"]
        if note is not None:
            self.conn.execute(
                "UPDATE collection SET deck_note = ? WHERE id = ?", (note, cid)
            )
            self.conn.commit()
        return {"card": card_name, "collection_id": cid}

    def fill_lands(self, deck_id: int) -> dict:
        """Auto-fill basic lands proportionally based on pip distribution."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        cards = self.deck_repo.get_cards(deck_id)
        current_count = len(cards)

        commander_ci = self._get_commander_identity(deck_id)
        if commander_ci is None:
            raise ValueError("No commander assigned — cannot determine color identity")

        # Count existing lands
        existing_lands = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))

        # Determine land target
        color_count = len(commander_ci)
        land_target = LAND_COUNTS.get(color_count, 38)

        # How many more lands needed
        lands_to_add = max(0, min(land_target - existing_lands, DECK_SIZE - current_count))

        # Suggest utility lands before filling basics
        utility_suggestions = self._suggest_utility_lands(deck_id, commander_ci)

        if lands_to_add == 0:
            return {"added": 0, "message": "No lands needed",
                    "utility_suggestions": utility_suggestions}

        # Count pips for proportional distribution
        pip_counts = self._count_pips(cards)
        ci_colors = [c for c in commander_ci if c in "WUBRG"]

        if not ci_colors:
            return {"added": 0, "message": "Colorless commander — add lands manually",
                    "utility_suggestions": utility_suggestions}

        # Filter to colors in CI
        relevant_pips = {c: pip_counts.get(c, 0) for c in ci_colors}
        total_pips = sum(relevant_pips.values())

        added = {}
        remaining = lands_to_add
        for i, color in enumerate(ci_colors):
            if total_pips > 0:
                share = relevant_pips[color] / total_pips
            else:
                share = 1 / len(ci_colors)

            if i == len(ci_colors) - 1:
                n = remaining  # Last color gets remainder
            else:
                n = round(lands_to_add * share)
                remaining -= n

            land_name = [name for name, c in BASIC_LANDS.items() if c == color][0]
            for _ in range(n):
                copy_id = self._find_basic_land_copy(color, deck_id)
                if copy_id:
                    self.deck_repo.add_cards(deck_id, [copy_id], zone=ZONE_MAINBOARD)
                    added[land_name] = added.get(land_name, 0) + 1
                else:
                    break

        self.conn.commit()
        return {"added": sum(added.values()), "lands": added,
                "utility_suggestions": utility_suggestions}

    # ── Inspection ──────────────────────────────────────────────────

    def show_deck(self, deck_id: int) -> dict:
        """Show the deck grouped by type."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        cards = self.deck_repo.get_cards(deck_id)

        # Commander first
        commander = [c for c in cards if c.get("deck_zone") == ZONE_COMMANDER]
        rest = [c for c in cards if c.get("deck_zone") != ZONE_COMMANDER]

        # Group by type
        groups = {}
        for card in rest:
            type_line = card.get("type_line", "")
            group = self._type_group(type_line)
            groups.setdefault(group, []).append(card)

        return {
            "deck": deck,
            "commander": commander,
            "groups": {k: sorted(v, key=lambda c: c["name"]) for k, v in sorted(groups.items())},
            "total": len(cards),
        }

    def check_deck(self, deck_id: int) -> dict:
        """Validate deck against Commander rules."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        cards = self.deck_repo.get_cards(deck_id)
        issues = []

        # Count check
        total = len(cards)
        if total != DECK_SIZE:
            issues.append(f"Deck has {total} cards (need exactly {DECK_SIZE})")

        # Commander check
        commanders = [c for c in cards if c.get("deck_zone") == ZONE_COMMANDER]
        if not commanders:
            issues.append("No commander assigned")

        # Color identity check
        commander_ci = self._get_commander_identity(deck_id)
        if commander_ci is not None:
            for card in cards:
                card_ci = set(parse_json_array(card.get("color_identity", "[]")))
                if not card_ci.issubset(commander_ci):
                    issues.append(f"'{card['name']}' violates color identity")

        # Singleton check
        name_counts = {}
        for card in cards:
            name = card["name"]
            name_counts[name] = name_counts.get(name, 0) + 1
        for name, cnt in name_counts.items():
            if cnt > 1 and not self._is_basic_land(name) and not self._is_any_number(name, card.get("oracle_text")):
                issues.append(f"'{name}' appears {cnt} times (singleton rule)")

        # Land count
        land_count = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))
        if land_count < 30:
            issues.append(f"Only {land_count} lands (recommend at least 33)")

        return {"deck_id": deck_id, "total": total, "issues": issues, "valid": len(issues) == 0}

    def audit_deck(self, deck_id: int) -> dict:
        """Audit deck for category balance, curve, and next steps."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        cards = self.deck_repo.get_cards(deck_id)
        total = len(cards)

        # Category counts
        categories = {}
        for card in cards:
            for cat in self._classify_card(card):
                categories[cat] = categories.get(cat, 0) + 1

        # Land count
        land_count = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))
        categories["Lands"] = land_count

        # Infrastructure gaps
        gaps = {}
        for cat_name, cat_info in INFRASTRUCTURE.items():
            current = categories.get(cat_name, 0)
            minimum = cat_info["min"]
            if current < minimum:
                gaps[cat_name] = {"current": current, "minimum": minimum, "need": minimum - current}
        # Land gap
        if land_count < LAND_TARGET_DEFAULT:
            gaps["Lands"] = {"current": land_count, "minimum": LAND_TARGET_DEFAULT,
                             "need": LAND_TARGET_DEFAULT - land_count}

        # Mana curve — split by creature vs noncreature
        nonland = [c for c in cards if not self._is_land_type(c.get("type_line", ""))]
        creatures = [c for c in nonland if "Creature" in (c.get("type_line") or "")]
        noncreatures = [c for c in nonland if "Creature" not in (c.get("type_line") or "")]

        curve = {}
        creature_curve = {}
        noncreature_curve = {}
        for c in nonland:
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            curve[bucket] = curve.get(bucket, 0) + 1
        for c in creatures:
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            creature_curve[bucket] = creature_curve.get(bucket, 0) + 1
        for c in noncreatures:
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            noncreature_curve[bucket] = noncreature_curve.get(bucket, 0) + 1

        # Average CMC
        if nonland:
            avg_cmc = sum(float(c.get("cmc", 0) or 0) for c in nonland) / len(nonland)
        else:
            avg_cmc = 0.0

        # Plan progress
        plan = self.get_plan(deck_id)
        plan_progress = self._get_plan_progress(deck_id, cards, plan)

        # Tag coverage and avg roles per card
        coverage, avg_roles, zero_role_cards = self._tag_coverage(nonland)

        # Next steps
        next_steps = self._suggest_next_steps(
            deck_id, total, cards, gaps, plan, plan_progress,
            zero_role_cards,
        )

        return {
            "deck_id": deck_id,
            "total": total,
            "categories": categories,
            "gaps": gaps,
            "curve": curve,
            "creature_curve": creature_curve,
            "noncreature_curve": noncreature_curve,
            "avg_cmc": round(avg_cmc, 2),
            "avg_cmc_target": AVG_CMC_TARGET,
            "plan": plan,
            "plan_progress": plan_progress,
            "coverage": coverage,
            "avg_roles": avg_roles,
            "zero_role_cards": zero_role_cards,
            "next_steps": next_steps,
        }

    # ── Plan ────────────────────────────────────────────────────────

    def set_plan(self, deck_id: int, targets: dict) -> dict:
        """Store a build plan with numeric targets as JSON in decks.plan."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")
        plan_json = json.dumps({"targets": targets})
        self.deck_repo.update(deck_id, {"plan": plan_json})
        self.conn.commit()
        return {"deck_id": deck_id, "targets": targets}

    def get_plan(self, deck_id: int) -> Optional[dict]:
        """Parse plan JSON from deck."""
        deck = self.deck_repo.get(deck_id)
        if not deck or not deck.get("plan"):
            return None
        return json.loads(deck["plan"])

    def clear_plan(self, deck_id: int) -> dict:
        """Clear the build plan."""
        self.deck_repo.update(deck_id, {"plan": None})
        self.conn.commit()
        return {"deck_id": deck_id}

    # ── Utilities ───────────────────────────────────────────────────

    def query_db(self, sql: str) -> List[dict]:
        """Execute a read-only SELECT query."""
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        rows = self.conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    # ── Private helpers ─────────────────────────────────────────────

    def _resolve_card(self, name: str):
        """Resolve a card by name (exact, case-insensitive, DFC, or substring)."""
        card = self.card_repo.get_by_name(name) or self.card_repo.search_by_name(name)
        if not card:
            results = self.card_repo.search_cards_by_name(name, limit=1)
            card = results[0] if results else None
        if not card:
            raise ValueError(f"Card not found: '{name}' (run `mtg cache all` to populate)")
        return card

    def _validate_commander(self, oracle_id: str, name: str, type_line: Optional[str]) -> None:
        """Validate that a card is a legal commander."""
        is_legendary_creature = type_line and "Legendary" in type_line and "Creature" in type_line

        card = self.card_repo.get(oracle_id)
        has_commander_text = card and card.oracle_text and "can be your commander" in card.oracle_text.lower()

        if not is_legendary_creature and not has_commander_text:
            raise ValueError(f"'{name}' is not a legendary creature and cannot be a commander")

        printings = self.printing_repo.get_by_oracle_id(oracle_id)
        if not printings:
            raise ValueError(f"No printings found for '{name}' (run `mtg cache all` to populate)")

        for p in printings:
            if p.raw_json:
                data = json.loads(p.raw_json)
                legality = data.get("legalities", {}).get("commander")
                if legality == "legal":
                    return
                elif legality == "banned":
                    raise ValueError(f"'{name}' is banned in Commander")

        if not any(p.raw_json for p in printings):
            raise ValueError(f"No card data for '{name}' — run `mtg cache all` to populate")

    def _get_commander_identity(self, deck_id: int) -> Optional[Set[str]]:
        """Get the color identity set from the commander card."""
        commanders = self.deck_repo.get_cards(deck_id, zone=ZONE_COMMANDER)
        if not commanders:
            return None
        ci = set()
        for c in commanders:
            ci.update(parse_json_array(c.get("color_identity", "[]")))
        return ci

    def _classify_card(self, card: dict) -> set:
        """Classify a card into infrastructure categories using tags."""
        categories = set()
        oracle_id = card.get("oracle_id")
        if not oracle_id:
            return categories
        rows = self.conn.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = ?", (oracle_id,)
        ).fetchall()
        card_tags = {row["tag"] for row in rows}
        for cat_name, cat_info in INFRASTRUCTURE.items():
            if card_tags & cat_info["tags"]:
                categories.add(cat_name)
        return categories

    def _get_card_tags(self, oracle_id: str) -> set:
        """Get all tags for a card."""
        rows = self.conn.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = ?", (oracle_id,)
        ).fetchall()
        return {row["tag"] for row in rows}

    def _find_best_copy(self, oracle_id: str, deck_id: int) -> Optional[int]:
        """Find the best unassigned owned copy by bling score."""
        rows = self.conn.execute(
            """SELECT c.id, c.finish, p.frame_effects, p.full_art, p.promo, p.promo_types
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               WHERE p.oracle_id = ?
                 AND c.status = 'owned'
                 AND c.deck_id IS NULL
                 AND c.binder_id IS NULL
               ORDER BY c.id""",
            (oracle_id,),
        ).fetchall()

        if not rows:
            return None

        best_id = None
        best_score = -1
        for row in rows:
            score = self._bling_score(row)
            if score > best_score:
                best_score = score
                best_id = row["id"]

        return best_id

    def _explain_no_copy(self, card_name: str, oracle_id: str) -> str:
        """Explain why no copy is available for a card."""
        # Check if owned but in another deck
        in_deck = self.conn.execute(
            """SELECT c.id, d.name AS deck_name
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN decks d ON c.deck_id = d.id
               WHERE p.oracle_id = ? AND c.status = 'owned'""",
            (oracle_id,),
        ).fetchone()
        if in_deck:
            return f"No unassigned copy of '{card_name}' — it's in deck '{in_deck['deck_name']}'"

        # Check if owned but in a binder
        in_binder = self.conn.execute(
            """SELECT c.id, b.name AS binder_name
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN binders b ON c.binder_id = b.id
               WHERE p.oracle_id = ? AND c.status = 'owned'""",
            (oracle_id,),
        ).fetchone()
        if in_binder:
            return f"No unassigned copy of '{card_name}' — it's in binder '{in_binder['binder_name']}'"

        return f"No owned copy of '{card_name}' available"

    def _find_basic_land_copy(self, color: str, deck_id: int) -> Optional[int]:
        """Find an unassigned basic land copy for the given color."""
        land_names = [name for name, c in {**BASIC_LANDS, **SNOW_BASICS}.items() if c == color]
        if not land_names:
            return None
        placeholders = ",".join("?" * len(land_names))
        row = self.conn.execute(
            f"""SELECT c.id
                FROM collection c
                JOIN printings p ON c.printing_id = p.printing_id
                JOIN cards card ON p.oracle_id = card.oracle_id
                WHERE card.name IN ({placeholders})
                  AND c.status = 'owned'
                  AND c.deck_id IS NULL
                  AND c.binder_id IS NULL
                LIMIT 1""",
            land_names,
        ).fetchone()
        return row["id"] if row else None

    def _bling_score(self, row) -> int:
        """Calculate a bling score for a card copy."""
        score = 0
        finish = row["finish"] if isinstance(row, dict) else row["finish"]
        if finish == "foil":
            score += BLING_WEIGHTS["finish_foil"]
        elif finish == "etched":
            score += BLING_WEIGHTS["finish_etched"]

        frame_effects = parse_json_array(row["frame_effects"]) if row["frame_effects"] else []
        for effect in frame_effects:
            if effect == "extendedart":
                score += BLING_WEIGHTS["frame_extended"]
            elif effect == "showcase":
                score += BLING_WEIGHTS["frame_showcase"]
            elif effect == "borderless":
                score += BLING_WEIGHTS["frame_borderless"]

        if row["full_art"]:
            score += BLING_WEIGHTS["full_art"]
        if row["promo"]:
            score += BLING_WEIGHTS["promo"]

        return score

    def _cards_in_deck_by_name(self, deck_id: int, card_name: str) -> List[dict]:
        """Find cards in a deck by name."""
        rows = self.conn.execute(
            """SELECT c.id, c.printing_id, card.name
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               WHERE c.deck_id = ? AND card.name = ?""",
            (deck_id, card_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_deck_tally(self, deck_id: int) -> dict:
        """Get running total and category counts for a deck."""
        cards = self.deck_repo.get_cards(deck_id)
        categories = {}
        for card in cards:
            for cat in self._classify_card(card):
                categories[cat] = categories.get(cat, 0) + 1
        land_count = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))
        categories["Lands"] = land_count
        return {"total": len(cards), "categories": categories}

    def _get_plan_progress(self, deck_id: int, cards: List[dict],
                           plan: Optional[dict]) -> Optional[dict]:
        """Get plan progress by counting cards with matching tags.

        Plan targets are tag names from card_tags, plus the special
        value "lands" which is counted by type line.
        """
        if not plan or "targets" not in plan:
            return None

        targets = plan["targets"]
        progress = {}

        # Count lands separately (not a tag)
        land_count = sum(
            1 for c in cards if self._is_land_type(c.get("type_line", ""))
        )

        # Count tags for all cards in deck
        tag_counts: dict[str, int] = {}
        for card in cards:
            oracle_id = card.get("oracle_id")
            if not oracle_id:
                continue
            card_tags = self._get_card_tags(oracle_id)
            for tag in card_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        for target_name, target_count in targets.items():
            if target_name == "lands":
                current = land_count
            else:
                current = tag_counts.get(target_name, 0)
            progress[target_name] = {"current": current, "target": target_count}
        return progress

    def _tag_coverage(self, nonland_cards: List[dict]) -> tuple:
        """Compute tag coverage stats for nonland cards.

        Returns (coverage_pct, avg_roles, zero_role_card_names).
        """
        if not nonland_cards:
            return 0.0, 0.0, []

        total_roles = 0
        covered = 0
        zero_role = []

        for card in nonland_cards:
            oracle_id = card.get("oracle_id")
            if not oracle_id:
                zero_role.append(card.get("name", "?"))
                continue
            tags = self._get_card_tags(oracle_id)
            n = len(tags)
            total_roles += n
            if n > 0:
                covered += 1
            else:
                zero_role.append(card.get("name", "?"))

        n_cards = len(nonland_cards)
        coverage = round(covered / n_cards * 100, 1) if n_cards else 0.0
        avg_roles = round(total_roles / n_cards, 1) if n_cards else 0.0
        return coverage, avg_roles, zero_role

    def _suggest_utility_lands(self, deck_id: int, commander_ci: Set[str]) -> List[dict]:
        """Find owned unassigned nonbasic lands in commander CI, sorted by EDHREC rank."""
        rows = self.conn.execute(
            """SELECT DISTINCT card.name, card.oracle_id, card.color_identity,
                      p.set_code, p.raw_json
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               WHERE c.status = 'owned'
                 AND c.deck_id IS NULL
                 AND c.binder_id IS NULL
                 AND card.type_line LIKE '%Land%'
                 AND card.type_line NOT LIKE '%Basic%'
                 AND card.oracle_id NOT IN (
                     SELECT p2.oracle_id FROM collection c2
                     JOIN printings p2 ON c2.printing_id = p2.printing_id
                     WHERE c2.deck_id = ?
                 )
               ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
               LIMIT 50""",
            (deck_id,),
        ).fetchall()

        suggestions = []
        seen = set()
        for row in rows:
            row_dict = dict(row)
            name = row_dict["name"]
            if name in seen:
                continue
            # Check color identity subset
            card_ci = set(parse_json_array(row_dict.get("color_identity", "[]")))
            if not card_ci.issubset(commander_ci):
                continue
            edhrec_rank = None
            if row_dict.get("raw_json"):
                data = json.loads(row_dict["raw_json"])
                edhrec_rank = data.get("edhrec_rank")
            seen.add(name)
            suggestions.append({
                "name": name,
                "edhrec_rank": edhrec_rank,
                "set_code": row_dict.get("set_code"),
            })
            if len(suggestions) >= 10:
                break
        return suggestions

    def _count_pips(self, cards: List[dict]) -> dict:
        """Count color pip distribution from mana costs."""
        pip_counts = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
        for card in cards:
            mana_cost = card.get("mana_cost") or ""
            for color in pip_counts:
                pip_counts[color] += mana_cost.count(f"{{{color}}}")
        return pip_counts

    def _land_target(self, color_count: int) -> int:
        """Get recommended land count from LAND_COUNTS."""
        return LAND_COUNTS.get(color_count, 38)

    def _is_basic_land(self, name: str) -> bool:
        """Check if a card is a basic land."""
        return name in BASIC_LANDS or name in SNOW_BASICS or name == "Wastes"

    def _is_any_number(self, name: str, oracle_text: Optional[str] = None) -> bool:
        """Check if a card can have any number in a deck."""
        return name in ANY_NUMBER_CARDS

    def _is_land_type(self, type_line: str) -> bool:
        """Check if a type line indicates a land."""
        return "Land" in type_line if type_line else False

    def _type_group(self, type_line: str) -> str:
        """Map a type line to a display group."""
        if not type_line:
            return "Other"
        for group in ["Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker", "Land"]:
            if group in type_line:
                return group
        return "Other"

    def _suggest_next_steps(self, deck_id: int, total: int, cards: List[dict],
                            gaps: dict, plan: Optional[dict],
                            plan_progress: Optional[dict],
                            zero_role_cards: Optional[List[str]] = None) -> List[str]:
        """Generate context-sensitive next steps."""
        steps = []

        if total <= 1:
            steps.append("Discuss strategy with the user before adding cards:")
            steps.append("  1. How does this deck win? (2-3 specific win conditions)")
            steps.append("  2. What does the deck DO on turns 3-6?")
            steps.append("  3. What does the commander contribute to the game plan?")
            return steps

        if plan is None:
            steps.append("Set a plan with sub-role targets before filling slots")

        # Infrastructure gaps
        infra_cats = set(INFRASTRUCTURE.keys())
        infra_gaps = {k: v for k, v in gaps.items() if k in infra_cats}
        if infra_gaps:
            for cat, info in infra_gaps.items():
                steps.append(
                    f"{cat}: need {info['need']} more (have {info['current']}/{info['minimum']})"
                )

        # Plan phase: infra met but plan targets not met
        if plan_progress and not infra_gaps:
            unfilled = {r: p for r, p in plan_progress.items() if p["current"] < p["target"]}
            if unfilled:
                steps.append("Fill plan sub-roles:")
                for role, prog in unfilled.items():
                    steps.append(f"  {role}: {prog['current']}/{prog['target']}")

        # Flag zero-role cards as swap candidates
        if zero_role_cards and len(zero_role_cards) <= 5:
            steps.append(
                f"Cards with no tags (swap candidates): {', '.join(zero_role_cards)}"
            )
        elif zero_role_cards:
            steps.append(
                f"{len(zero_role_cards)} cards have no tags — consider swapping for multi-role alternatives"
            )

        if total > DECK_SIZE:
            over = total - DECK_SIZE
            steps.append(f"Cut {over} nonland card(s) to reach {DECK_SIZE}")

        land_count = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))
        nonland_target = DECK_SIZE - LAND_TARGET_DEFAULT
        nonland_count = total - land_count

        if total < DECK_SIZE:
            if nonland_count >= nonland_target and land_count < LAND_TARGET_DEFAULT:
                steps.append("Ready to fill lands")
            else:
                remaining = DECK_SIZE - total
                steps.append(f"{remaining} slots remaining")

        if total == DECK_SIZE:
            # Salt check
            high_salt = []
            for card in cards:
                salt = self.conn.execute(
                    "SELECT salt_score FROM salt_scores WHERE card_name = ?",
                    (card["name"],)
                ).fetchone()
                if salt and salt["salt_score"] > 2.0:
                    high_salt.append((card["name"], salt["salt_score"]))
            if high_salt:
                steps.append("High salt cards (>2.0):")
                for name, score in high_salt:
                    steps.append(f"  {name}: {score:.1f}")

            # Curve warnings — per type group
            nonland = [c for c in cards if not self._is_land_type(c.get("type_line", ""))]
            creatures = [c for c in nonland if "Creature" in (c.get("type_line") or "")]
            noncreatures = [c for c in nonland if "Creature" not in (c.get("type_line") or "")]

            for group_name, group_cards, targets in [
                ("Creature", creatures, CREATURE_CURVE_TARGETS),
                ("Noncreature", noncreatures, NONCREATURE_CURVE_TARGETS),
            ]:
                group_curve = {}
                for c in group_cards:
                    cmc = int(c.get("cmc", 0) or 0)
                    bucket = min(cmc, 7)
                    group_curve[bucket] = group_curve.get(bucket, 0) + 1
                for bucket, (lo, hi) in targets.items():
                    cnt = group_curve.get(bucket, 0)
                    if cnt < lo or cnt > hi:
                        label = f"{bucket}+" if bucket == 7 else str(bucket)
                        steps.append(f"Curve: {group_name} CMC {label} has {cnt} (target {lo}-{hi})")

            steps.append("Ready for final validation and description")

        return steps
