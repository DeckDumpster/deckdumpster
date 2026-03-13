"""Deck builder service for Commander/EDH deck construction."""

import json
import math
import random
import sqlite3
from typing import List, Optional, Set

from mtg_collector.db.models import (
    CardRepository,
    CollectionRepository,
    Deck,
    DeckRepository,
    PrintingRepository,
    tag_validation_filter,
)
from mtg_collector.services.deck_builder.constants import (
    ANY_NUMBER_CARDS,
    AUTOFILL_WEIGHTS,
    AVG_CMC_TARGET,
    BASIC_LANDS,
    BLING_WEIGHTS,
    CREATURE_CURVE_LIMITS,
    CREATURE_CURVE_TARGETS,
    DB_SCHEMA_FOR_PLAN,
    DECK_SIZE,
    DEFAULT_FORMAT,
    DYNAMIC_WEIGHT_CURVE_FIT,
    DYNAMIC_WEIGHT_DEFICIT,
    DYNAMIC_WEIGHT_EXPONENT,
    DYNAMIC_WEIGHT_RARITY,
    INFRASTRUCTURE,
    LAND_COUNTS,
    LAND_TARGET_DEFAULT,
    LAND_WEIGHTS,
    NONCREATURE_CURVE_LIMITS,
    NONCREATURE_CURVE_TARGETS,
    PLAN_GENERATE_MAX_TOKENS,
    PLAN_GENERATE_MAX_TOOL_ROUNDS,
    PLAN_GENERATE_MODEL,
    PLAN_GENERATE_PROMPT,
    QUERY_DB_TOOL,
    SNOW_BASICS,
    ZONE_COMMANDER,
    ZONE_MAINBOARD,
)
from mtg_collector.utils import parse_json_array

# ── Autofill ranking weights ─────────────────────────────────────
# Default weights for autofill scoring. All weights are internal —
# no longer user-adjustable.
# Weight for deficit bonus in autofill scoring. Higher = prefer filling gaps
# over raw card quality. This scales the sum-of-deficit-ratios signal.


# Tag aliases — when autofill searches for a tag, also include cards
# with these related tags.  Covers Scryfall tagging gaps where a card
# fulfills a role but uses a more specific or adjacent tag name.
TAG_ALIASES: dict[str, list[str]] = {
    # ── Mass removal ──
    "boardwipe": ["multi-removal", "sweeper-one-sided"],
    "sweeper-one-sided": ["boardwipe", "multi-removal"],
    "multi-removal": ["boardwipe", "sweeper-one-sided"],
    # ── Targeted removal ──
    "removal": ["creature-removal", "artifact-removal", "enchantment-removal",
                 "planeswalker-removal", "removal-exile", "edict", "bounce"],
    "creature-removal": ["removal-toughness", "edict", "burn-creature"],
    "artifact-removal": ["disenchant"],
    "enchantment-removal": ["disenchant"],
    "disenchant": ["artifact-removal", "enchantment-removal"],
    # ── Ramp ──
    "ramp": ["mana-dork", "mana-rock", "extra-land", "cost-reducer"],
    "mana-dork": ["ramp"],
    "mana-rock": ["ramp"],
    "extra-land": ["ramp"],
    # ── Card draw / advantage ──
    "draw": ["repeatable-draw", "burst-draw", "impulse", "card-advantage"],
    "card-advantage": ["draw", "impulse", "tutor"],
    "repeatable-draw": ["draw", "curiosity-like"],
    "burst-draw": ["draw", "wheel"],
    "impulse": ["repeatable-impulsive-draw"],
    "tutor": ["card-advantage"],
    # ── Card filtering ──
    "loot": ["rummage", "discard-outlet"],
    "rummage": ["loot", "discard-outlet"],
    "discard-outlet": ["loot", "rummage"],
    # ── Recursion / reanimation ──
    "recursion": ["reanimate", "recursion-artifact", "recursion-permanent", "cheat-death"],
    "reanimate": ["recursion", "reanimate-cast"],
    "reanimate-cast": ["reanimate"],
    "recursion-artifact": ["recursion"],
    "recursion-permanent": ["recursion"],
    "recursion-land": ["recursion"],
    "cheat-death": ["cheat-death-self", "recursion"],
    "cheat-death-self": ["cheat-death"],
    # ── Evasion ──
    "evasion": ["gives-evasion", "gives-menace"],
    "gives-evasion": ["evasion"],
    # ── Token synergy ──
    "synergy-token": ["synergy-token-creature", "repeatable-creature-tokens",
                       "repeatable-token-generator", "multiple-bodies"],
    "synergy-token-creature": ["synergy-token", "repeatable-creature-tokens"],
    # ── Lifegain ──
    "lifegain": ["repeatable-lifegain"],
    "lifegain-matters": ["lifegain", "repeatable-lifegain"],
    "repeatable-lifegain": ["lifegain"],
    # ── Burn ──
    "burn": ["burn-creature", "burn-player", "pinger"],
    "burn-creature": ["burn", "pinger"],
    "burn-player": ["burn"],
    # ── Theft / control ──
    "theft-creature": ["theft-cast", "control-changing-effects"],
    "theft-cast": ["theft-creature", "control-changing-effects"],
    "control-changing-effects": ["theft-creature", "theft-cast"],
    # ── Sacrifice ──
    "sacrifice-outlet": ["synergy-token"],
    # ── Graveyard hate ──
    "graveyard-hate": ["graveyard-to-library"],
    # ── Mill ──
    "mill": ["self-mill"],
    "self-mill": ["mill"],
    # ── Counters ──
    "counters-matter": ["gives-pp-counters", "gives-mm-counters"],
    "gives-pp-counters": ["counters-matter"],
    # ── Infrastructure broad categories ──
    # These expand to all sub-tags in an infrastructure group so autofill
    # searches across all related tags for a single broad target.
    "Ramp": sorted(INFRASTRUCTURE["Ramp"]["tags"]),
    "Card Advantage": sorted(INFRASTRUCTURE["Card Advantage"]["tags"]),
    "Targeted Disruption": sorted(INFRASTRUCTURE["Targeted Disruption"]["tags"]),
    "Mass Disruption": sorted(INFRASTRUCTURE["Mass Disruption"]["tags"]),
}



class DeckContext:
    """All deck-scoped query modifiers, derived once from deck_id.

    Centralizes hypothetical-vs-physical branching so callers never need
    to remember to pass a flag — just call _deck_context(deck_id).
    """

    def __init__(self, hypothetical: bool):
        self.hypothetical = hypothetical

    def availability_sql(self) -> str:
        """SQL fragment restricting to unassigned cards (physical only)."""
        if self.hypothetical:
            return ""
        return "AND c.deck_id IS NULL AND c.binder_id IS NULL"

    def exclude_deck_sql(self, deck_id: int) -> tuple[str, list]:
        """SQL clause + params to exclude cards already in this deck."""
        if self.hypothetical:
            return (
                "AND card.oracle_id NOT IN "
                "(SELECT oracle_id FROM deck_expected_cards WHERE deck_id = ?)",
                [deck_id],
            )
        return (
            "AND c.deck_id IS NULL "
            "AND card.oracle_id NOT IN "
            "(SELECT p2.oracle_id FROM collection c2 "
            "JOIN printings p2 ON c2.printing_id = p2.printing_id "
            "WHERE c2.deck_id = ?)",
            [deck_id],
        )

    def card_source_sql(self) -> tuple[str, str]:
        """(FROM clause, WHERE clause) for querying cards IN this deck."""
        if self.hypothetical:
            return (
                "FROM deck_expected_cards e"
                " JOIN cards card ON e.oracle_id = card.oracle_id",
                "e.deck_id = ?",
            )
        return (
            "FROM collection c"
            " JOIN printings p ON c.printing_id = p.printing_id"
            " JOIN cards card ON p.oracle_id = card.oracle_id",
            "c.deck_id = ?",
        )

    def card_source_ext_sql(self) -> tuple[str, str]:
        """Extended card source with printings for custom queries."""
        if self.hypothetical:
            return (
                "FROM deck_expected_cards e"
                " JOIN cards card ON e.oracle_id = card.oracle_id"
                " LEFT JOIN printings p ON p.printing_id = ("
                "   SELECT MIN(p2.printing_id) FROM printings p2"
                "   WHERE p2.oracle_id = card.oracle_id)",
                "e.deck_id = ?",
            )
        card_from, card_where = self.card_source_sql()
        return card_from, card_where

    def count_expr(self) -> str:
        """SQL expression for counting cards (SUM for hypothetical, COUNT for physical)."""
        if self.hypothetical:
            return "COALESCE(SUM(e.quantity), 0)"
        return "COUNT(*)"

    def tag_count_expr(self) -> str:
        """SQL expression for counting distinct cards per tag."""
        if self.hypothetical:
            return "COALESCE(SUM(e.quantity), 0)"
        return "COUNT(DISTINCT p.oracle_id)"


class DeckBuilderService:
    """Service for building Commander/EDH decks from owned cards."""

    def __init__(self, conn: sqlite3.Connection, api_key: str | None = None):
        self.conn = conn
        self.api_key = api_key
        self.card_repo = CardRepository(conn)
        self.printing_repo = PrintingRepository(conn)
        self.collection_repo = CollectionRepository(conn)
        self.deck_repo = DeckRepository(conn)

    def _deck_context(self, deck_id: int) -> DeckContext:
        """Build a DeckContext from a deck_id, deriving hypothetical from the DB."""
        deck = self.deck_repo.get(deck_id)
        return DeckContext(bool(deck and deck.get("hypothetical")))

    @staticmethod
    def _card_qty(card: dict) -> int:
        """Get effective quantity for a card row (hypothetical cards have quantity > 1)."""
        return card.get("quantity") or 1

    # ── Deck lifecycle ──────────────────────────────────────────────

    def create_deck(self, commander_name: str, hypothetical: bool = False) -> dict:
        """Create a new Commander deck with the given commander."""
        card = self._resolve_card(commander_name)

        # Validate it's a legal commander
        self._validate_commander(card.oracle_id, card.name, card.type_line)

        # Create deck
        deck = Deck(id=None, name=card.name, format=DEFAULT_FORMAT,
                    hypothetical=hypothetical)
        deck_id = self.deck_repo.add(deck)

        if hypothetical:
            # Add commander as expected card
            self.conn.execute(
                "INSERT INTO deck_expected_cards (deck_id, oracle_id, zone, quantity)"
                " VALUES (?, ?, ?, 1)",
                (deck_id, card.oracle_id, ZONE_COMMANDER),
            )
        else:
            # Find best owned copy and assign as commander
            copy_id = self._find_best_copy(card.oracle_id, deck_id)
            if copy_id:
                self.deck_repo.add_cards(deck_id, [copy_id], zone=ZONE_COMMANDER)

        self.conn.commit()
        return {"deck_id": deck_id, "commander": card.name}

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
                 count: int = 1) -> dict:
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

    def swap_card(self, deck_id: int, out_name: str, in_name: str) -> dict:
        """Swap one card for another in the deck."""
        out_result = self.remove_card(deck_id, out_name, count=1)
        in_result = self.add_card(deck_id, in_name)
        return {"removed": out_result["card"], "added": in_result["card"]}

    def suggest_lands(self, deck_id: int) -> dict:
        """Suggest nonbasic + basic lands for a deck, scored and ready for review."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        ctx = self._deck_context(deck_id)
        if ctx.hypothetical:
            cards = self.deck_repo.get_expected_cards_full(deck_id)
            current_count = sum(c.get("quantity", 1) for c in cards)
        else:
            cards = self.deck_repo.get_cards(deck_id)
            current_count = len(cards)

        commander_ci = self._get_commander_identity(deck_id)
        if commander_ci is None:
            raise ValueError("No commander assigned — cannot determine color identity")

        existing_lands = sum(1 for c in cards if self._is_land_type(c.get("type_line", "")))
        color_count = len(commander_ci)
        land_target = LAND_COUNTS.get(color_count, 38)
        lands_needed = max(0, min(land_target - existing_lands, DECK_SIZE - current_count))

        ci_colors = [c for c in commander_ci if c in "WUBRG"]
        pip_counts = self._count_pips(cards)
        relevant_pips = {c: pip_counts.get(c, 0) for c in ci_colors}
        total_pips = sum(relevant_pips.values())
        pip_fractions = {}
        for c in ci_colors:
            pip_fractions[c] = relevant_pips[c] / total_pips if total_pips > 0 else 1.0 / max(len(ci_colors), 1)

        result = {
            "deck_id": deck_id,
            "hypothetical": ctx.hypothetical,
            "land_target": land_target,
            "existing_lands": existing_lands,
            "pip_fractions": pip_fractions,
            "suggestions": {"nonbasic": [], "basic": []},
        }

        if lands_needed == 0 or not ci_colors:
            return result

        # --- Nonbasic candidates ---
        ci_clauses = self._ci_exclusion_sql(commander_ci)
        avail = ctx.availability_sql()
        exclude_sql, exclude_params = ctx.exclude_deck_sql(deck_id)
        rows = self.conn.execute(
            f"""SELECT card.oracle_id, card.name, card.type_line, card.oracle_text,
                       p.set_code, p.collector_number, p.printing_id,
                       p.image_uri, p.rarity,
                       json_extract(p.raw_json, '$.produced_mana') AS produced_mana,
                       json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank,
                       MIN(c.id) AS collection_id, c.finish,
                       p.frame_effects, p.full_art, p.promo
                FROM cards card
                JOIN printings p ON p.oracle_id = card.oracle_id
                JOIN collection c ON c.printing_id = p.printing_id
                WHERE card.type_line LIKE '%Land%'
                  AND card.type_line NOT LIKE '%Basic%'
                  AND c.status = 'owned'
                  {avail}
                  {exclude_sql}
                  {ci_clauses}
                GROUP BY card.oracle_id
                ORDER BY edhrec_rank ASC NULLS LAST""",
            exclude_params,
        ).fetchall()
        candidates = [dict(r) for r in rows]

        if candidates:
            scored = self._score_land_candidates(candidates, ci_colors, pip_fractions)
            nonbasic_picks = scored[:lands_needed]
            result["suggestions"]["nonbasic"] = nonbasic_picks
            basic_needed = lands_needed - len(nonbasic_picks)
        else:
            basic_needed = lands_needed

        # --- Basic land pool ---
        # Fetch enough basics for the full lands_needed (not just the remainder)
        # so the UI can swap nonbasics for basics without re-fetching.
        basic_pool_size = lands_needed
        if basic_pool_size > 0 and ci_colors:
            remaining = basic_pool_size
            for i, color in enumerate(ci_colors):
                if i == len(ci_colors) - 1:
                    n = remaining
                else:
                    n = round(basic_pool_size * pip_fractions[color])
                    remaining -= n
                if n <= 0:
                    continue
                land_name = [name for name, c in BASIC_LANDS.items() if c == color][0]
                oid_row = self.conn.execute(
                    "SELECT oracle_id FROM cards WHERE name = ?", (land_name,)
                ).fetchone()
                use_count = round(basic_needed * pip_fractions[color]) if basic_needed > 0 else 0
                if i == len(ci_colors) - 1:
                    use_count = basic_needed - sum(
                        b["count"] for b in result["suggestions"]["basic"]
                    )

                # Hypothetical: no physical copies needed, just oracle_id + count
                if ctx.hypothetical:
                    use_count = max(0, use_count)
                    basic_entry = {
                        "name": land_name, "count": use_count,
                        "collection_ids": [],
                        "oracle_id": oid_row["oracle_id"] if oid_row else None,
                    }
                    result["suggestions"]["basic"].append(basic_entry)
                    continue

                # Physical: find owned unassigned copies
                cids = self._find_basic_land_copies(color, deck_id, n)
                if not cids:
                    continue
                use_count = max(0, min(use_count, len(cids)))
                basic_entry = {
                    "name": land_name, "count": use_count,
                    "collection_ids": cids,
                    "oracle_id": oid_row["oracle_id"] if oid_row else None,
                }
                result["suggestions"]["basic"].append(basic_entry)

        return result

    def _score_land_candidates(self, candidates: list[dict], ci_colors: list[str],
                                pip_fractions: dict[str, float]) -> list[dict]:
        """Score and rank nonbasic land candidates."""
        # Collect edhrec ranks and bling scores for min-max normalization
        edhrec_ranks = [c["edhrec_rank"] for c in candidates if c["edhrec_rank"] is not None]
        edhrec_min = min(edhrec_ranks) if edhrec_ranks else 0
        edhrec_max = max(edhrec_ranks) if edhrec_ranks else 1
        edhrec_range = max(edhrec_max - edhrec_min, 1)

        scored = []
        bling_raw = []
        for c in candidates:
            # Color coverage
            produced = json.loads(c["produced_mana"]) if c["produced_mana"] else []
            oracle = (c["oracle_text"] or "").lower()
            # Fetch lands: null produced_mana but search for basic land
            if not produced and "search your library for a basic land" in oracle:
                produced = list(ci_colors)
            coverage = sum(pip_fractions.get(color, 0) for color in ci_colors if color in produced)

            # Skip lands that produce none of the commander's colors
            if coverage == 0:
                continue

            # Untapped
            enters_tapped = "enters the battlefield tapped" in oracle or "enters tapped" in oracle
            has_unless = "unless" in oracle
            if not enters_tapped:
                untapped_score = 1.0
            elif has_unless:
                untapped_score = 0.7
            else:
                untapped_score = 0.0

            # EDHREC (inverted, normalized)
            if c["edhrec_rank"] is not None:
                edhrec_score = 1.0 - (c["edhrec_rank"] - edhrec_min) / edhrec_range
            else:
                edhrec_score = 0.0

            bling = self._bling_score(c)
            bling_raw.append((len(scored), bling))

            scored.append({
                "candidate": c, "coverage": coverage,
                "untapped_score": untapped_score, "edhrec_score": edhrec_score,
                "bling": bling, "produced": produced, "enters_tapped": enters_tapped,
            })

        bling_max = max((b for _, b in bling_raw), default=1) or 1

        final = []
        for entry in scored:
            c = entry["candidate"]
            bling_norm = entry["bling"] / bling_max if bling_max > 0 else 0.0
            jitter = random.random()

            total = (
                LAND_WEIGHTS["color_coverage"] * entry["coverage"]
                + LAND_WEIGHTS["untapped"] * entry["untapped_score"]
                + LAND_WEIGHTS["edhrec"] * entry["edhrec_score"]
                + LAND_WEIGHTS["bling"] * bling_norm
                + LAND_WEIGHTS["random"] * jitter
            )

            final.append({
                "name": c["name"],
                "oracle_id": c["oracle_id"],
                "collection_id": c["collection_id"],
                "score": round(total, 3),
                "produced_mana": entry["produced"],
                "enters_tapped": entry["enters_tapped"],
                "set_code": c["set_code"],
                "collector_number": c["collector_number"],
                "image_uri": c["image_uri"],
                "rarity": c["rarity"],
                "finish": c["finish"],
            })

        final.sort(key=lambda x: x["score"], reverse=True)
        return final

    def fill_lands(self, deck_id: int) -> dict:
        """Auto-fill lands using suggest_lands(), then add all suggestions."""
        suggestions = self.suggest_lands(deck_id)
        nonbasic = suggestions["suggestions"]["nonbasic"]
        basic = suggestions["suggestions"]["basic"]

        added = {}
        # Add nonbasic lands
        for land in nonbasic:
            self.deck_repo.add_cards(deck_id, [land["collection_id"]], zone=ZONE_MAINBOARD)
            added[land["name"]] = added.get(land["name"], 0) + 1

        # Add basic lands (only use 'count' IDs, not the full pool)
        for group in basic:
            use_ids = group["collection_ids"][:group["count"]]
            if use_ids:
                self.deck_repo.add_cards(deck_id, use_ids, zone=ZONE_MAINBOARD)
                added[group["name"]] = added.get(group["name"], 0) + len(use_ids)

        self.conn.commit()
        total_added = sum(added.values())
        if total_added == 0:
            return {"added": 0, "message": "No lands needed"}
        return {"added": total_added, "lands": added}

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

        ctx = self._deck_context(deck_id)
        if ctx.hypothetical:
            cards = self.deck_repo.get_expected_cards_full(deck_id)
        else:
            cards = self.deck_repo.get_cards(deck_id)
        issues = []

        # Count check
        total = sum(self._card_qty(c) for c in cards)
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
            name_counts[name] = name_counts.get(name, 0) + self._card_qty(card)
        for name, cnt in name_counts.items():
            if cnt > 1 and not self._is_basic_land(name) and not self._is_any_number(name, card.get("oracle_text")):
                issues.append(f"'{name}' appears {cnt} times (singleton rule)")

        # Land count
        land_count = sum(self._card_qty(c) for c in cards if self._is_land_type(c.get("type_line", "")))
        if land_count < 30:
            issues.append(f"Only {land_count} lands (recommend at least 33)")

        return {"deck_id": deck_id, "total": total, "issues": issues, "valid": len(issues) == 0}

    def audit_deck(self, deck_id: int) -> dict:
        """Audit deck for category balance, curve, and next steps."""
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        ctx = self._deck_context(deck_id)
        if ctx.hypothetical:
            cards = self.deck_repo.get_expected_cards_full(deck_id)
        else:
            cards = self.deck_repo.get_cards(deck_id)
        qty = self._card_qty
        total = sum(qty(c) for c in cards)

        # Category counts
        categories = {}
        for card in cards:
            q = qty(card)
            for cat in self._classify_card(card):
                categories[cat] = categories.get(cat, 0) + q

        # Land count
        land_count = sum(qty(c) for c in cards if self._is_land_type(c.get("type_line", "")))
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
            curve[bucket] = curve.get(bucket, 0) + qty(c)
        for c in creatures:
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            creature_curve[bucket] = creature_curve.get(bucket, 0) + qty(c)
        for c in noncreatures:
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            noncreature_curve[bucket] = noncreature_curve.get(bucket, 0) + qty(c)

        # Average CMC (weighted by quantity)
        nonland_total = sum(qty(c) for c in nonland)
        if nonland_total:
            avg_cmc = sum(float(c.get("cmc", 0) or 0) * qty(c) for c in nonland) / nonland_total
        else:
            avg_cmc = 0.0

        # Plan progress
        plan = self.get_plan(deck_id)
        plan_progress = self._get_plan_progress(deck_id, cards, plan, ctx)

        # Tag coverage and avg roles per card
        coverage, avg_roles, zero_role_cards = self._tag_coverage(deck_id, ctx)

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

    def _normalize_targets(self, targets: dict) -> dict:
        """Convert all target values to canonical dict shape for consumers."""
        result = {}
        for key, val in targets.items():
            if isinstance(val, dict) and "type" in val:
                result[key] = val  # already normalized
            elif key == "lands":
                count = val if isinstance(val, (int, float)) else val.get("count", 0)
                result[key] = {"count": int(count), "label": "lands", "type": "lands"}
            elif isinstance(val, dict):
                result[key] = {"count": int(val["count"]), "label": val["label"],
                               "type": "query", "query": val["query"]}
            else:
                result[key] = {"count": int(val), "label": key.replace("-", " "), "type": "tag"}
        return result

    def _denormalize_targets(self, targets: dict) -> dict:
        """Convert normalized targets back to storage format."""
        result = {}
        for key, val in targets.items():
            if isinstance(val, dict) and "type" in val:
                if val["type"] == "query":
                    result[key] = {"count": val["count"], "query": val["query"], "label": val["label"]}
                else:
                    result[key] = val["count"]
            else:
                result[key] = val  # already in storage format
        return result

    def generate_plan_variants(self, deck_id: int, progress_cb=None):
        """Generate 2 plan variants for a Commander deck using Claude.

        Args:
            deck_id: The deck to generate plans for.
            progress_cb: Optional callback(message: str) for status updates.

        Returns:
            dict with "variants" key containing the generated plans.

        Raises:
            ValueError: If deck not found or no commander assigned.
            RuntimeError: If plan generation exceeds max tool rounds.
        """
        import re

        import anthropic

        from mtg_collector.services.retry import anthropic_retry

        def emit(msg):
            if progress_cb:
                progress_cb(msg)

        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError("Deck not found")

        ctx = self._deck_context(deck_id)
        card_from, card_where = ctx.card_source_sql()
        zone_col = "e.zone" if ctx.hypothetical else "c.deck_zone"
        commander = self.conn.execute(
            f"""SELECT card.name, card.type_line, card.mana_cost, card.colors,
                      card.color_identity, card.oracle_text
               {card_from}
               WHERE {card_where} AND {zone_col} = 'commander'
               LIMIT 1""",
            (deck_id,),
        ).fetchone()

        if not commander:
            raise ValueError("No commander assigned to this deck")
        commander = dict(commander)

        color_identity = commander.get("color_identity") or "[]"
        if isinstance(color_identity, str):
            try:
                color_identity = json.loads(color_identity)
            except (ValueError, TypeError):
                color_identity = []
        colors_str = ", ".join(color_identity) if color_identity else "Colorless"

        tag_rows = self.conn.execute(
            "SELECT tag, COUNT(*) AS cnt FROM card_tags "
            "WHERE tag NOT LIKE 'type:%' GROUP BY tag ORDER BY cnt DESC"
        ).fetchall()
        tag_list = ", ".join(f"{r['tag']} ({r['cnt']})" for r in tag_rows)

        infra_lines = []
        for cat, info in INFRASTRUCTURE.items():
            tags_str = ", ".join(sorted(info["tags"]))
            infra_lines.append(f"- **{cat}** (min {info['min']}): {tags_str}")

        prompt = PLAN_GENERATE_PROMPT.format(
            commander_name=commander["name"],
            commander_type=commander.get("type_line", "Unknown"),
            commander_mana_cost=commander.get("mana_cost", "Unknown"),
            colors_str=colors_str,
            commander_oracle_text=commander.get("oracle_text", "N/A"),
            tag_list=tag_list,
            db_schema=DB_SCHEMA_FOR_PLAN,
            infra_lines="\n".join(infra_lines),
        )

        def execute_safe_query(sql):
            sql = sql.strip()
            lower = sql.lower()
            for forbidden in ("drop ", "delete ", "insert ", "update ",
                              "alter ", "create ", "attach ", "detach ", "pragma "):
                if forbidden in lower:
                    return {"error": f"Forbidden: {forbidden.strip()} not allowed"}
            self.conn.execute("SAVEPOINT query_db_check")
            try:
                rows = self.conn.execute(sql).fetchall()
                result = [dict(r) for r in rows[:20]]
                return {"rows": result, "count": len(result)}
            except sqlite3.OperationalError as e:
                return {"error": str(e)}
            finally:
                try:
                    self.conn.execute("ROLLBACK TO SAVEPOINT query_db_check")
                except Exception:
                    pass
                try:
                    self.conn.execute("RELEASE SAVEPOINT query_db_check")
                except Exception:
                    pass

        emit("Analyzing commander and generating deck plans...")

        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": prompt}]

        for _round in range(PLAN_GENERATE_MAX_TOOL_ROUNDS + 1):
            response = anthropic_retry(lambda: client.messages.create(
                model=PLAN_GENERATE_MODEL,
                max_tokens=PLAN_GENERATE_MAX_TOKENS,
                tools=[QUERY_DB_TOOL],
                messages=messages,
            ))

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        sql = block.input.get("sql", "")
                        emit(f"Testing query: {sql[:80]}...")
                        result = execute_safe_query(sql)
                        if "error" in result:
                            emit(f"Query error: {result['error']}")
                        else:
                            emit(f"Query returned {result['count']} rows")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Final text response — extract JSON
            collected_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    collected_text += block.text

            json_text = collected_text.strip()
            fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', json_text, re.DOTALL)
            if fence_match:
                json_text = fence_match.group(1).strip()
            else:
                brace_start = json_text.find('{')
                if brace_start >= 0:
                    json_text = json_text[brace_start:]
                    depth = 0
                    for i, ch in enumerate(json_text):
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                json_text = json_text[:i + 1]
                                break

            result = json.loads(json_text)
            for variant in result.get("variants", []):
                if "targets" in variant:
                    variant["targets"] = self._normalize_targets(variant["targets"])
                    # Ensure all infrastructure categories are present with minimums
                    for cat_name, cat_info in INFRASTRUCTURE.items():
                        if cat_name not in variant["targets"]:
                            variant["targets"][cat_name] = {
                                "count": cat_info["min"],
                                "label": cat_name,
                                "type": "tag",
                            }
            return result

        raise RuntimeError("Plan generation exceeded maximum tool rounds")

    def set_plan(self, deck_id: int, targets: dict) -> dict:
        """Store a build plan with numeric targets as JSON in decks.plan.

        Target values can be:
        - int: tag-based role with this count (backward compatible)
        - dict with {count, query, label}: custom SQL WHERE clause role
        - normalized dict with {count, label, type, query?}: from API round-trip
        """
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        # Denormalize first so validation works on storage format
        storage_targets = self._denormalize_targets(targets)

        # Validate each target
        for key, val in storage_targets.items():
            if isinstance(val, (int, float)):
                continue
            if isinstance(val, dict):
                if "count" not in val or "query" not in val or "label" not in val:
                    raise ValueError(
                        f"Custom query target '{key}' must have 'count', 'query', and 'label'"
                    )
                if not isinstance(val["count"], (int, float)):
                    raise ValueError(f"Custom query target '{key}' count must be a number")
                # Validate the SQL is syntactically valid
                self._safe_execute_custom_query(val["query"], validate_only=True)
            else:
                raise ValueError(
                    f"Target '{key}' must be an integer or a dict with count/query/label"
                )

        # Preserve existing weights when updating targets
        existing_plan = self.get_plan(deck_id)
        new_plan = {"targets": storage_targets}
        if existing_plan and "weights" in existing_plan:
            new_plan["weights"] = existing_plan["weights"]
        self.deck_repo.update(deck_id, {"plan": json.dumps(new_plan)})
        self.conn.commit()
        return {"deck_id": deck_id, "targets": self._normalize_targets(storage_targets)}

    def get_plan(self, deck_id: int) -> Optional[dict]:
        """Parse plan JSON from deck. Targets are normalized to canonical dict shape."""
        deck = self.deck_repo.get(deck_id)
        if not deck or not deck.get("plan"):
            return None
        plan = json.loads(deck["plan"])
        if "targets" in plan:
            plan["targets"] = self._normalize_targets(plan["targets"])
        return plan

    def clear_plan(self, deck_id: int) -> dict:
        """Clear the build plan."""
        self.deck_repo.update(deck_id, {"plan": None})
        self.conn.commit()
        return {"deck_id": deck_id}

    # ── Autofill ──────────────────────────────────────────────────

    def autofill(self, deck_id: int, progress_cb=None, reset: bool = False) -> dict:
        """Suggest cards to fill plan targets from the user's collection.

        Picks one card at a time. Each candidate is scored with static
        weights (edhrec, bling, novelty, etc.) plus a dynamic deficit
        bonus: categories that still need cards contribute more to a
        card's score. Multi-role cards naturally win because they
        accumulate deficit bonus from multiple categories.

        If reset=True, removes all non-commander cards from the deck first.

        Returns suggestions grouped by the category with the highest
        deficit at pick time. Does NOT add cards — caller decides which
        to accept.
        """
        deck = self.deck_repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        ctx = self._deck_context(deck_id)

        plan = self.get_plan(deck_id)
        if not plan or "targets" not in plan:
            raise ValueError("No plan set — generate a plan first")

        # Reset: remove all non-commander cards before suggesting
        if reset:
            if ctx.hypothetical:
                self.conn.execute(
                    "DELETE FROM deck_expected_cards WHERE deck_id = ? AND zone != 'commander'",
                    (deck_id,),
                )
                self.conn.commit()
                if progress_cb:
                    progress_cb("Cleared expected cards from deck")
            else:
                all_cards = self.deck_repo.get_cards(deck_id)
                non_commander_ids = [
                    c["id"] for c in all_cards
                    if c.get("deck_zone") != ZONE_COMMANDER
                ]
                if non_commander_ids:
                    self.deck_repo.remove_cards(deck_id, non_commander_ids)
                self.conn.commit()
                if progress_cb:
                    progress_cb(f"Cleared {len(non_commander_ids)} cards from deck")

        targets = plan["targets"]
        effective_w = dict(AUTOFILL_WEIGHTS)
        if ctx.hypothetical:
            cards_in_deck = self.deck_repo.get_expected_cards_full(deck_id)
        else:
            cards_in_deck = self.deck_repo.get_cards(deck_id)
        commander_ci = self._get_commander_identity(deck_id)
        if commander_ci is None:
            raise ValueError("No commander assigned")

        # Compute budget: total nonland slots available
        commander_count = sum(1 for c in cards_in_deck if c.get("deck_zone") == ZONE_COMMANDER)
        land_target_val = targets.get("lands")
        land_target = land_target_val["count"] if land_target_val else LAND_TARGET_DEFAULT
        nonland_budget = DECK_SIZE - commander_count - land_target
        existing_nonland = sum(
            1 for c in cards_in_deck
            if c.get("deck_zone") != ZONE_COMMANDER
            and not self._is_land_type(c.get("type_line", ""))
        )
        remaining_budget = nonland_budget - existing_nonland

        # ── Category tracking ──
        # Build a unified category state: {key: {target, current, tags_set}}
        # For infrastructure categories, current = distinct oracle_ids with any sub-tag.
        # For regular tags, current = count of cards with that tag.
        # For custom queries, current = count of cards matching the query.
        cat_state: dict[str, dict] = {}
        deck_oids = {c.get("oracle_id") for c in cards_in_deck if c.get("oracle_id")}

        for key, val in targets.items():
            if key == "lands":
                continue
            entry: dict = {"target": val["count"], "type": val["type"], "label": val["label"]}
            if key in INFRASTRUCTURE:
                # Count distinct oracle_ids matching any sub-tag
                sub_tags = INFRASTRUCTURE[key]["tags"]
                entry["sub_tags"] = sub_tags
                oids_in_cat: set[str] = set()
                for card in cards_in_deck:
                    oid = card.get("oracle_id")
                    if oid and self._get_card_tags(oid) & sub_tags:
                        oids_in_cat.add(oid)
                entry["current"] = len(oids_in_cat)
                entry["oids"] = oids_in_cat
            elif val["type"] == "query":
                entry["query"] = val["query"]
                if deck_oids:
                    oid_list = ",".join(f"'{o}'" for o in deck_oids)
                    cnt = self.conn.execute(
                        f"SELECT COUNT(DISTINCT card.oracle_id) AS cnt "  # noqa: S608
                        f"FROM cards card "
                        f"JOIN printings p ON p.oracle_id = card.oracle_id "
                        f"WHERE ({val['query']}) "
                        f"AND card.oracle_id IN ({oid_list})"
                    ).fetchone()["cnt"]
                    entry["current"] = cnt
                else:
                    entry["current"] = 0
            else:
                # Regular tag
                tag_count = 0
                for card in cards_in_deck:
                    oid = card.get("oracle_id")
                    if oid and key in self._get_card_tags(oid):
                        tag_count += 1
                entry["current"] = tag_count
            cat_state[key] = entry

        # Fetch per-commander EDHREC data
        if ctx.hypothetical:
            commanders = [c for c in cards_in_deck if c.get("deck_zone") == "commander"]
        else:
            commanders = self.deck_repo.get_cards(deck_id, zone=ZONE_COMMANDER)
        commander_name = commanders[0]["name"] if commanders else None
        edhrec_data: dict[str, float] = {}
        if commander_name:
            from mtg_collector.services.deck_builder.edhrec import EdhrecCommander
            edhrec_client = EdhrecCommander(self.conn)
            edhrec_data = edhrec_client.get_inclusion_map(commander_name)
            if progress_cb and edhrec_data:
                progress_cb(f"Loaded EDHREC data for {commander_name}")

        ci_clauses = self._ci_exclusion_sql(commander_ci)

        # Create validator for on-pick tag validation
        validator = None
        if self.api_key:
            from mtg_collector.services.deck_builder.tag_validator import TagValidator
            validator = TagValidator(self.conn)

        exclude_oids: set[str] = set(deck_oids)

        # Build expanded plan tag set for scoring
        expanded_plan_tags: set[str] = set()
        for tag, val in targets.items():
            if tag == "lands" or val["type"] == "query":
                continue
            expanded_plan_tags.add(tag)
            for alias in TAG_ALIASES.get(tag, []):
                expanded_plan_tags.add(alias)

        curve_state = self._compute_curve_state(cards_in_deck)

        # ── Fetch candidate pool ──
        # One big query: all owned cards in CI matching ANY plan/infra tag.
        if progress_cb:
            progress_cb("Fetching candidate pool...")
        all_tag_targets = [t for t in expanded_plan_tags
                           if t not in INFRASTRUCTURE]
        pool = self._query_tag_candidates_pool(
            all_tag_targets, deck_id, commander_ci, ci_clauses, exclude_oids,
        )
        # Also fetch custom query candidates and merge
        for key, val in targets.items():
            if val["type"] == "query":
                custom_cands = self._query_custom_candidates(
                    val["query"], deck_id, commander_ci, ci_clauses,
                    exclude_oids, limit=200,
                )
                existing_oids = {c["oracle_id"] for c in pool}
                for c in custom_cands:
                    if c["oracle_id"] not in existing_oids:
                        pool.append(c)
                        existing_oids.add(c["oracle_id"])

        # Hard filter: never add lands during nonland autofill
        pool = [c for c in pool if "Land" not in (c.get("type_line") or "")]

        if progress_cb:
            progress_cb(f"Scoring {len(pool)} candidates...")

        # Pre-compute static scores for the whole pool
        pool = self._score_candidates(pool, edhrec_data=edhrec_data,
                                       plan_tags=expanded_plan_tags,
                                       curve_state=curve_state,
                                       weights=effective_w)

        # Batch-fetch tags for all candidates (for deficit bonus computation)
        pool_oids = [c["oracle_id"] for c in pool]
        tags_by_oid: dict[str, set[str]] = {}
        if pool_oids:
            placeholders = ",".join("?" for _ in pool_oids)
            rows = self.conn.execute(
                f"SELECT ct.oracle_id, ct.tag FROM card_tags ct "  # noqa: S608
                f"WHERE ct.oracle_id IN ({placeholders})"
                f" AND {tag_validation_filter()}",
                pool_oids,
            ).fetchall()
            for row in rows:
                tags_by_oid.setdefault(row["oracle_id"], set()).add(row["tag"])
            # Apply hard-coded tag rules
            type_by_oid = {c["oracle_id"]: c.get("type_line", "") for c in pool}
            for oid, tags in tags_by_oid.items():
                self._clean_tags(tags, type_by_oid.get(oid, ""))

        # Pre-check which candidates match each custom query
        custom_match: dict[str, set[str]] = {}  # query_key -> set of oracle_ids
        for key, val in targets.items():
            if val["type"] == "query" and pool_oids:
                oid_list = ",".join(f"'{o}'" for o in pool_oids)
                matched = self.conn.execute(
                    f"SELECT DISTINCT card.oracle_id FROM cards card "  # noqa: S608
                    f"JOIN printings p ON p.oracle_id = card.oracle_id "
                    f"WHERE ({val['query']}) AND card.oracle_id IN ({oid_list})"
                ).fetchall()
                custom_match[key] = {r["oracle_id"] for r in matched}

        # Index pool by oracle_id for fast removal
        pool_by_oid: dict[str, dict] = {c["oracle_id"]: c for c in pool}

        # ── Pick loop: one card at a time ──
        suggestions: dict[str, dict] = {}
        pick_number = 0
        total_budget = remaining_budget  # snapshot for fill_ratio

        while remaining_budget > 0 and pool_by_oid:
            # Check if any category still has a deficit
            any_deficit = False
            for cs in cat_state.values():
                if cs["current"] < cs["target"]:
                    any_deficit = True
                    break

            if not any_deficit:
                break  # all targets met

            # Score each remaining candidate: static_score + deficit_bonus
            best_card = None
            best_score = -1.0
            best_category = None

            for oid, card in pool_by_oid.items():
                card_tags = tags_by_oid.get(oid, set())

                # Deficit bonus = max deficit ratio across all matching
                # categories (infra + plan). Each category contributes
                # its own (target - current) / target ratio independently.
                deficit_bonus = 0.0
                top_cat = None

                for cat_key, cs in cat_state.items():
                    if cs["current"] >= cs["target"]:
                        continue
                    cat_matches = False
                    if cat_key in INFRASTRUCTURE:
                        cat_matches = bool(card_tags & cs["sub_tags"])
                    elif cs["type"] == "query":
                        cat_matches = oid in custom_match.get(cat_key, set())
                    else:
                        cat_matches = cat_key in card_tags
                    if cat_matches:
                        cat_deficit = (cs["target"] - cs["current"]) / cs["target"]
                        if cat_deficit > deficit_bonus:
                            deficit_bonus = cat_deficit
                            top_cat = cat_key

                if deficit_bonus == 0:
                    continue  # card doesn't help any deficit category

                fill_ratio = pick_number / total_budget if total_budget > 0 else 0.0
                total_score = self._weighted_score(
                    card, effective_w, deficit=deficit_bonus, fill_ratio=fill_ratio,
                )
                if total_score > best_score:
                    best_score = total_score
                    best_card = card
                    best_category = top_cat

            if best_card is None:
                break  # no candidates help any remaining deficit

            # Validate tags before committing the pick
            pick_oid = best_card["oracle_id"]
            if validator:
                old_tags = tags_by_oid.get(pick_oid, set()).copy()
                validator._validate_card(best_card)
                # Refresh tags from DB after validation
                fresh_rows = self.conn.execute(
                    f"SELECT ct.tag FROM card_tags ct WHERE ct.oracle_id = ?"
                    f" AND {tag_validation_filter()}", (pick_oid,)
                ).fetchall()
                new_tags = {r["tag"] for r in fresh_rows}
                tags_by_oid[pick_oid] = new_tags
                if new_tags != old_tags:
                    if progress_cb:
                        lost = old_tags - new_tags
                        if lost:
                            progress_cb(f"Invalidated tags for {best_card['name']}: {', '.join(sorted(lost))}")
                    # Tags changed — skip this pick, it'll be re-scored next iteration
                    continue

            # Pick this card
            pick_tags = tags_by_oid.get(pick_oid, set())
            del pool_by_oid[pick_oid]
            remaining_budget -= 1
            pick_number += 1

            # Update category counts
            for cat_key, cs in cat_state.items():
                if cs["current"] >= cs["target"]:
                    continue
                matches = False
                if cat_key in INFRASTRUCTURE:
                    if pick_tags & cs["sub_tags"] and pick_oid not in cs.get("oids", set()):
                        matches = True
                        cs.setdefault("oids", set()).add(pick_oid)
                elif cs["type"] == "query":
                    matches = pick_oid in custom_match.get(cat_key, set())
                else:
                    matches = cat_key in pick_tags
                if matches:
                    cs["current"] += 1

            # Update curve state
            cmc = int(best_card.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            type_line = best_card.get("type_line") or ""
            if "Creature" in type_line:
                curve_state["creature"][bucket] = curve_state["creature"].get(bucket, 0) + 1
            else:
                curve_state["noncreature"][bucket] = curve_state["noncreature"].get(bucket, 0) + 1

            # Record suggestion under its primary (highest deficit) category
            cat_label = best_category
            if cat_label not in suggestions:
                cs = cat_state[cat_label]
                suggestions[cat_label] = {
                    "target": cs["target"],
                    "current": cs["current"],
                    "cards": [],
                }
                if cs["type"] == "query":
                    suggestions[cat_label]["label"] = cs["label"]
            suggestions[cat_label]["cards"].append({
                "oracle_id": best_card["oracle_id"],
                "name": best_card["name"],
                "mana_cost": best_card["mana_cost"],
                "cmc": best_card["cmc"],
                "type_line": best_card["type_line"],
                "set_code": best_card["set_code"],
                "collector_number": best_card["collector_number"],
                "collection_id": best_card["collection_id"],
                "score": round(best_score, 3),
                "edhrec_rank": best_card["edhrec_rank"],
                "tag_count": best_card["tag_count"],
            })

            if progress_cb and pick_number % 10 == 0:
                filled = sum(1 for cs in cat_state.values() if cs["current"] >= cs["target"])
                progress_cb(f"Picked {pick_number} cards ({filled}/{len(cat_state)} categories filled)")

        # ── Fill remaining budget with best pool cards ──
        # All targets are met but the deck isn't full yet. Pick the
        # highest-quality remaining pool cards (by static score) that
        # match at least one plan or infra tag.
        if remaining_budget > 0 and pool_by_oid:
            if progress_cb:
                progress_cb(f"Filling {remaining_budget} remaining slots by quality")
            remaining_sorted = sorted(
                pool_by_oid.values(),
                key=lambda c: -self._weighted_score(c, effective_w, fill_ratio=1.0),
            )
            for card in remaining_sorted:
                if remaining_budget <= 0:
                    break
                oid = card["oracle_id"]
                card_tags = tags_by_oid.get(oid, set())

                # Find the best category to attribute this card to
                best_cat = None
                best_cat_deficit = -1
                for cat_key, cs in cat_state.items():
                    cat_matches = False
                    if cat_key in INFRASTRUCTURE:
                        cat_matches = bool(card_tags & cs["sub_tags"])
                    elif cs["type"] == "query":
                        cat_matches = oid in custom_match.get(cat_key, set())
                    else:
                        cat_matches = cat_key in card_tags
                    if cat_matches:
                        # Prefer categories still furthest from target
                        gap = cs["target"] - cs["current"]
                        if gap > best_cat_deficit:
                            best_cat_deficit = gap
                            best_cat = cat_key
                if not best_cat:
                    best_cat = "_quality"  # generic quality pick, no tag match

                remaining_budget -= 1
                pick_number += 1

                # Update category counts
                pick_tags = card_tags
                for cat_key, cs in cat_state.items():
                    cat_matches = False
                    if cat_key in INFRASTRUCTURE:
                        if pick_tags & cs["sub_tags"] and oid not in cs.get("oids", set()):
                            cat_matches = True
                            cs.setdefault("oids", set()).add(oid)
                    elif cs["type"] == "query":
                        cat_matches = oid in custom_match.get(cat_key, set())
                    else:
                        cat_matches = cat_key in pick_tags
                    if cat_matches:
                        cs["current"] += 1

                if best_cat not in suggestions:
                    if best_cat in cat_state:
                        cs = cat_state[best_cat]
                        suggestions[best_cat] = {
                            "target": cs["target"],
                            "current": cs["current"],
                            "cards": [],
                        }
                        if cs["type"] == "query":
                            suggestions[best_cat]["label"] = cs["label"]
                    else:
                        suggestions[best_cat] = {
                            "target": remaining_budget + pick_number,
                            "current": 0,
                            "cards": [],
                        }
                fill_score = self._weighted_score(card, effective_w, fill_ratio=1.0)
                suggestions[best_cat]["cards"].append({
                    "oracle_id": card["oracle_id"],
                    "name": card["name"],
                    "mana_cost": card["mana_cost"],
                    "cmc": card["cmc"],
                    "type_line": card["type_line"],
                    "set_code": card["set_code"],
                    "collector_number": card["collector_number"],
                    "collection_id": card["collection_id"],
                    "score": round(fill_score, 3),
                    "edhrec_rank": card["edhrec_rank"],
                    "tag_count": card["tag_count"],
                })

        # Update suggestion entries with final category counts
        for cat_key, data in suggestions.items():
            if cat_key in cat_state:
                data["current"] = cat_state[cat_key]["current"]

        result = {"deck_id": deck_id, "suggestions": suggestions}
        if not self.api_key:
            result["unvalidated"] = True
        return result

    def _ci_exclusion_sql(self, commander_ci: Set[str]) -> str:
        """Build SQL WHERE clauses to exclude colors outside commander CI."""
        all_colors = {"W", "U", "B", "R", "G"}
        excluded = all_colors - commander_ci
        clauses = ""
        for color in excluded:
            clauses += (
                f" AND (card.color_identity IS NULL"
                f" OR card.color_identity NOT LIKE '%{color}%')"
            )
        return clauses

    def _safe_execute_custom_query(self, where_clause: str, *,
                                    validate_only: bool = False,
                                    limit: int = 20) -> list[dict]:
        """Execute a custom WHERE clause safely against the card DB.

        Uses a savepoint so any side effects are rolled back. Only SELECT
        operations are permitted — the SQLite authorizer blocks writes.

        If validate_only=True, just checks syntax and returns [].
        """
        # Block obviously dangerous patterns
        lower = where_clause.lower()
        for forbidden in ("drop ", "delete ", "insert ", "update ", "alter ",
                          "create ", "attach ", "detach ", "pragma "):
            if forbidden in lower:
                raise ValueError(f"Forbidden SQL keyword in custom query: {forbidden.strip()}")

        test_sql = f"""
            SELECT card.oracle_id, card.name
            FROM cards card
            JOIN printings p ON p.oracle_id = card.oracle_id
            WHERE {where_clause}
            LIMIT 1
        """
        self.conn.execute("SAVEPOINT custom_query_check")
        try:
            self.conn.execute(test_sql)
        except sqlite3.OperationalError as e:
            self.conn.execute("ROLLBACK TO SAVEPOINT custom_query_check")
            raise ValueError(f"Invalid custom query SQL: {e}") from e
        finally:
            self.conn.execute("RELEASE SAVEPOINT custom_query_check")

        if validate_only:
            return []

        # Full query with all candidate columns
        full_sql = f"""
            SELECT card.oracle_id, card.name, card.type_line,
                   card.mana_cost, card.cmc, card.oracle_text,
                   p.set_code, p.collector_number, p.raw_json,
                   MIN(c.id) AS collection_id,
                   s.released_at,
                   COUNT(ct_all.tag) AS tag_count,
                   COALESCE(salt.salt_score, 1.0) AS salt_score,
                   MAX(CASE WHEN p.full_art = 1
                            OR p.frame_effects LIKE '%borderless%'
                            OR p.frame_effects LIKE '%extendedart%'
                            OR p.frame_effects LIKE '%showcase%'
                       THEN 1 ELSE 0 END) AS is_bling
            FROM cards card
            JOIN printings p ON p.oracle_id = card.oracle_id
            JOIN collection c ON c.printing_id = p.printing_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN card_tags ct_all ON ct_all.oracle_id = card.oracle_id
              AND {tag_validation_filter("ct_all")}
            LEFT JOIN salt_scores salt ON salt.card_name = card.name
            WHERE {where_clause}
              AND c.status = 'owned'
              AND card.type_line NOT LIKE '%Basic Land%'
              AND card.type_line NOT LIKE 'Token%'
            GROUP BY card.oracle_id
            ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
            LIMIT {int(limit)}
        """  # noqa: S608
        rows = self.conn.execute(full_sql).fetchall()
        return [dict(r) for r in rows]

    def _compute_curve_state(self, cards: List[dict]) -> dict:
        """Compute current mana curve counts from a list of cards.

        Returns {creature: {0: N, 1: N, ...}, noncreature: {0: N, 1: N, ...}}.
        """
        state: dict[str, dict[int, int]] = {"creature": {}, "noncreature": {}}
        for c in cards:
            type_line = c.get("type_line") or ""
            if self._is_land_type(type_line):
                continue
            if c.get("deck_zone") == ZONE_COMMANDER:
                continue
            cmc = int(c.get("cmc", 0) or 0)
            bucket = min(cmc, 7)
            group = "creature" if "Creature" in type_line else "noncreature"
            state[group][bucket] = state[group].get(bucket, 0) + 1
        return state

    def _query_custom_candidates(self, where_clause: str, deck_id: int,
                                  commander_ci: Set[str], ci_clauses: str,
                                  exclude_oids: Set[str],
                                  limit: int | None = None) -> list[dict]:
        """Query owned cards matching a custom WHERE clause, in CI, not excluded."""
        exclude_list = ",".join(f"'{oid}'" for oid in exclude_oids) if exclude_oids else "''"
        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        avail = self._deck_context(deck_id).availability_sql()

        query = f"""
            SELECT card.oracle_id, card.name, card.type_line,
                   card.mana_cost, card.cmc, card.oracle_text,
                   p.set_code, p.collector_number, p.raw_json,
                   MIN(c.id) AS collection_id,
                   s.released_at,
                   COUNT(ct_all.tag) AS tag_count,
                   COALESCE(salt.salt_score, 1.0) AS salt_score,
                   MAX(CASE WHEN p.full_art = 1
                            OR p.frame_effects LIKE '%borderless%'
                            OR p.frame_effects LIKE '%extendedart%'
                            OR p.frame_effects LIKE '%showcase%'
                       THEN 1 ELSE 0 END) AS is_bling
            FROM cards card
            JOIN printings p ON p.oracle_id = card.oracle_id
            JOIN collection c ON c.printing_id = p.printing_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN card_tags ct_all ON ct_all.oracle_id = card.oracle_id
              AND {tag_validation_filter("ct_all")}
            LEFT JOIN salt_scores salt ON salt.card_name = card.name
            WHERE ({where_clause})
              AND c.status = 'owned'
              {avail}
              AND card.oracle_id NOT IN ({exclude_list})
              AND card.type_line NOT LIKE '%Basic Land%'
              AND card.type_line NOT LIKE 'Token%'
              {ci_clauses}
            GROUP BY card.oracle_id
            ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
            {limit_clause}
        """  # noqa: S608
        rows = self.conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def _query_tag_candidates(self, tag: str, deck_id: int,
                               commander_ci: Set[str], ci_clauses: str,
                               exclude_oids: Set[str],
                               limit: int | None = None) -> list[dict]:
        """Query owned cards with a specific tag, in CI, not excluded."""
        exclude_list = ",".join(f"'{oid}'" for oid in exclude_oids) if exclude_oids else "''"
        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        avail = self._deck_context(deck_id).availability_sql()

        # Expand tag to include aliases
        tags = [tag] + TAG_ALIASES.get(tag, [])
        tag_placeholders = ",".join("?" for _ in tags)

        query = f"""
            SELECT card.oracle_id, card.name, card.type_line,
                   card.mana_cost, card.cmc, card.oracle_text,
                   p.set_code, p.collector_number, p.raw_json,
                   MIN(c.id) AS collection_id,
                   s.released_at,
                   COUNT(ct_all.tag) AS tag_count,
                   COALESCE(salt.salt_score, 1.0) AS salt_score,
                   MAX(CASE WHEN p.full_art = 1
                            OR p.frame_effects LIKE '%borderless%'
                            OR p.frame_effects LIKE '%extendedart%'
                            OR p.frame_effects LIKE '%showcase%'
                       THEN 1 ELSE 0 END) AS is_bling
            FROM card_tags ct
            JOIN cards card ON ct.oracle_id = card.oracle_id
            JOIN printings p ON p.oracle_id = card.oracle_id
            JOIN collection c ON c.printing_id = p.printing_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN card_tags ct_all ON ct_all.oracle_id = card.oracle_id
              AND {tag_validation_filter("ct_all")}
            LEFT JOIN salt_scores salt ON salt.card_name = card.name
            WHERE ct.tag IN ({tag_placeholders})
              AND {tag_validation_filter()}
              AND c.status = 'owned'
              {avail}
              AND card.oracle_id NOT IN ({exclude_list})
              AND card.type_line NOT LIKE '%Basic Land%'
              AND card.type_line NOT LIKE 'Token%'
              {ci_clauses}
            GROUP BY card.oracle_id
            ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
            {limit_clause}
        """  # noqa: S608
        rows = self.conn.execute(query, tags).fetchall()
        return [dict(r) for r in rows]

    def _query_tag_candidates_pool(self, tags: list[str], deck_id: int,
                                    commander_ci: Set[str], ci_clauses: str,
                                    exclude_oids: Set[str]) -> list[dict]:
        """Fetch all owned cards matching ANY of the given tags, in CI."""
        if not tags:
            return []
        exclude_list = ",".join(f"'{oid}'" for oid in exclude_oids) if exclude_oids else "''"
        avail = self._deck_context(deck_id).availability_sql()
        tag_placeholders = ",".join("?" for _ in tags)

        query = f"""
            SELECT card.oracle_id, card.name, card.type_line,
                   card.mana_cost, card.cmc, card.oracle_text,
                   p.set_code, p.collector_number, p.raw_json,
                   MIN(c.id) AS collection_id,
                   s.released_at,
                   COUNT(ct_all.tag) AS tag_count,
                   COALESCE(salt.salt_score, 1.0) AS salt_score,
                   MAX(CASE WHEN p.full_art = 1
                            OR p.frame_effects LIKE '%borderless%'
                            OR p.frame_effects LIKE '%extendedart%'
                            OR p.frame_effects LIKE '%showcase%'
                       THEN 1 ELSE 0 END) AS is_bling
            FROM card_tags ct
            JOIN cards card ON ct.oracle_id = card.oracle_id
            JOIN printings p ON p.oracle_id = card.oracle_id
            JOIN collection c ON c.printing_id = p.printing_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN card_tags ct_all ON ct_all.oracle_id = card.oracle_id
              AND {tag_validation_filter("ct_all")}
            LEFT JOIN salt_scores salt ON salt.card_name = card.name
            WHERE ct.tag IN ({tag_placeholders})
              AND {tag_validation_filter()}
              AND c.status = 'owned'
              {avail}
              AND card.oracle_id NOT IN ({exclude_list})
              AND card.type_line NOT LIKE '%Basic Land%'
              AND card.type_line NOT LIKE 'Token%'
              {ci_clauses}
            GROUP BY card.oracle_id
            ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
        """  # noqa: S608
        rows = self.conn.execute(query, tags).fetchall()
        return [dict(r) for r in rows]

    def _query_creature_candidates(self, deck_id: int,
                                    commander_ci: Set[str], ci_clauses: str,
                                    exclude_oids: Set[str],
                                    limit: int | None = None) -> list[dict]:
        """Query owned creatures in CI, not excluded — fallback for autofill."""
        exclude_list = ",".join(f"'{oid}'" for oid in exclude_oids) if exclude_oids else "''"
        limit_clause = f"LIMIT {int(limit)}" if limit else ""
        avail = self._deck_context(deck_id).availability_sql()

        query = f"""
            SELECT card.oracle_id, card.name, card.type_line,
                   card.mana_cost, card.cmc, card.oracle_text,
                   p.set_code, p.collector_number, p.raw_json,
                   MIN(c.id) AS collection_id,
                   s.released_at,
                   COUNT(ct_all.tag) AS tag_count,
                   COALESCE(salt.salt_score, 1.0) AS salt_score,
                   MAX(CASE WHEN p.full_art = 1
                            OR p.frame_effects LIKE '%borderless%'
                            OR p.frame_effects LIKE '%extendedart%'
                            OR p.frame_effects LIKE '%showcase%'
                       THEN 1 ELSE 0 END) AS is_bling
            FROM cards card
            JOIN printings p ON p.oracle_id = card.oracle_id
            JOIN collection c ON c.printing_id = p.printing_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN card_tags ct_all ON ct_all.oracle_id = card.oracle_id
              AND {tag_validation_filter("ct_all")}
            LEFT JOIN salt_scores salt ON salt.card_name = card.name
            WHERE card.type_line LIKE '%Creature%'
              AND c.status = 'owned'
              {avail}
              AND card.oracle_id NOT IN ({exclude_list})
              AND card.type_line NOT LIKE '%Basic Land%'
              AND card.type_line NOT LIKE 'Token%'
              {ci_clauses}
            GROUP BY card.oracle_id
            ORDER BY json_extract(p.raw_json, '$.edhrec_rank') ASC NULLS LAST
            {limit_clause}
        """  # noqa: S608
        rows = self.conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def _score_candidates(self, candidates: list[dict],
                          edhrec_data: dict[str, float] | None = None,
                          plan_tags: set[str] | None = None,
                          curve_state: dict | None = None,
                          weights: dict | None = None) -> list[dict]:
        """Score a small set of candidates using composite ranking.

        Normalizes signals across the candidate set and computes a
        weighted sum. Returns the same list with a 'score' field added.

        If *edhrec_data* is provided (per-commander inclusion rates from
        EDHREC), the edhrec signal uses inclusion percentage (higher = more
        popular with this commander). Novelty uses inverse global EDHREC
        rank (higher rank number = less popular = more novel).

        If *plan_tags* is provided (expanded set of all plan categories +
        aliases), each candidate gets a plan_overlap score based on how
        many plan tags it matches.

        If *curve_state* is provided, cards in under-represented CMC
        buckets get a curve_fit boost.
        """
        if not candidates:
            return []

        edhrec_data = edhrec_data or {}
        plan_tags = plan_tags or set()

        # Batch-fetch card tags for plan overlap computation
        tags_by_oid: dict[str, set[str]] = {}
        if plan_tags:
            oids = [c["oracle_id"] for c in candidates]
            placeholders = ",".join("?" for _ in oids)
            rows = self.conn.execute(
                f"SELECT ct.oracle_id, ct.tag FROM card_tags ct "  # noqa: S608
                f"WHERE ct.oracle_id IN ({placeholders})"
                f" AND {tag_validation_filter()}",
                oids,
            ).fetchall()
            for row in rows:
                tags_by_oid.setdefault(row["oracle_id"], set()).add(row["tag"])

        # Extract raw signal values
        for c in candidates:
            # EDHREC rank from raw_json
            edhrec_rank = None
            price_usd = 0.0
            if c.get("raw_json"):
                data = json.loads(c["raw_json"])
                edhrec_rank = data.get("edhrec_rank")
                price_str = (data.get("prices") or {}).get("usd")
                if price_str:
                    try:
                        price_usd = float(price_str)
                    except (ValueError, TypeError):
                        pass

            c["edhrec_rank"] = edhrec_rank
            global_rank = edhrec_rank if edhrec_rank is not None else 999999
            c["_salt"] = c.get("salt_score") or 1.0
            c["_price"] = math.log1p(price_usd)

            # Plan overlap: count of plan tags this card matches
            card_tags = tags_by_oid.get(c["oracle_id"], set())
            c["_plan_overlap"] = len(card_tags & plan_tags)

            # EDHREC: per-commander inclusion rate (higher = more popular
            # with this general). Falls back to inverse global rank.
            inclusion_pct = edhrec_data.get(c["name"])
            if inclusion_pct is not None:
                c["_edhrec"] = inclusion_pct
            else:
                # Approximate: lower global rank → higher inclusion proxy
                c["_edhrec"] = 1.0 / math.log2(max(global_rank, 2))

            # Novelty: inverse global EDHREC rank (higher rank = less
            # popular overall = more interesting/unique choice)
            c["_novelty"] = math.log2(max(global_rank, 1))

            # Recency: days since 1993-01-01
            recency = 0
            if c.get("released_at"):
                try:
                    from datetime import datetime
                    dt = datetime.strptime(c["released_at"], "%Y-%m-%d")
                    recency = (dt - datetime(1993, 1, 1)).days
                except (ValueError, TypeError):
                    pass
            c["_recency"] = recency

            # Rarity: mythic=4, rare=3, uncommon=2, common=1
            rarity_map = {"M": 4, "R": 3, "U": 2, "C": 1, "P": 3, "L": 1, "T": 0}
            c["_rarity"] = rarity_map.get(c.get("rarity", "C"), 1)

            # Curve fit: deficit from target for this card's CMC bucket
            if curve_state:
                cmc = int(c.get("cmc", 0) or 0)
                bucket = min(cmc, 7)
                type_line = c.get("type_line") or ""
                if "Creature" in type_line:
                    cur = curve_state["creature"].get(bucket, 0)
                    tgt = CREATURE_CURVE_TARGETS.get(bucket, 0)
                else:
                    cur = curve_state["noncreature"].get(bucket, 0)
                    tgt = NONCREATURE_CURVE_TARGETS.get(bucket, 0)
                # Positive deficit = bucket needs more cards = higher score
                c["_curve_fit"] = max(tgt - cur, 0)
            else:
                c["_curve_fit"] = 0

        # Min-max normalize each signal to 0-1
        def _norm(key):
            vals = [c[key] for c in candidates]
            lo, hi = min(vals), max(vals)
            span = hi - lo
            if span == 0:
                for c in candidates:
                    c[key + "_n"] = 0.5
            else:
                for c in candidates:
                    c[key + "_n"] = (c[key] - lo) / span

        _norm("_edhrec")
        _norm("_salt")
        _norm("_price")
        _norm("_plan_overlap")
        _norm("_novelty")
        _norm("_recency")
        _norm("_rarity")
        _norm("_curve_fit")

        # Store random jitter once so it's stable across re-scores
        for c in candidates:
            c["_random"] = random.random()

        return candidates

    @staticmethod
    def _weighted_score(card: dict, weights: dict,
                        deficit: float = 0.0,
                        fill_ratio: float = 0.0) -> float:
        """Compute weighted score for a candidate card.

        Static weights (edhrec, bling, etc.) are constant. Dynamic weights:
        - deficit, curve_fit: exponential ramp (negligible until ~85%, dominant near 100%)
        - rarity: starts high (splashy picks early), linear decline 30%-80% fill
        """
        w = weights
        # Exponential ramp for deficit and curve_fit
        ramp = fill_ratio ** DYNAMIC_WEIGHT_EXPONENT
        deficit_w = DYNAMIC_WEIGHT_DEFICIT[0] + (DYNAMIC_WEIGHT_DEFICIT[1] - DYNAMIC_WEIGHT_DEFICIT[0]) * ramp
        curve_w = DYNAMIC_WEIGHT_CURVE_FIT[0] + (DYNAMIC_WEIGHT_CURVE_FIT[1] - DYNAMIC_WEIGHT_CURVE_FIT[0]) * ramp
        # Linear ramp-down for rarity
        r = DYNAMIC_WEIGHT_RARITY
        if fill_ratio <= r["start_at"]:
            rarity_w = r["start_weight"]
        elif fill_ratio >= r["end_at"]:
            rarity_w = r["end_weight"]
        else:
            t = (fill_ratio - r["start_at"]) / (r["end_at"] - r["start_at"])
            rarity_w = r["start_weight"] + (r["end_weight"] - r["start_weight"]) * t
        return (
            card["_edhrec_n"] * w["edhrec"]
            + (1.0 - card["_salt_n"]) * w["salt"]
            + card["_price_n"] * w["price"]
            + card["_plan_overlap_n"] * w["plan_overlap"]
            + card["_novelty_n"] * w["novelty"]
            + card["_recency_n"] * w["recency"]
            + card.get("is_bling", 0) * w["bling"]
            + card["_rarity_n"] * rarity_w
            + card.get("_random", 0) * w["random"]
            + card["_curve_fit_n"] * curve_w
            + deficit * deficit_w
        )

    # ── Tag inspection ─────────────────────────────────────────────

    def get_validated_tags(self, oracle_id: str) -> dict:
        """Return tags for a card, validating on-demand if API key is available.

        Checks the card_tag_validations cache first.  For any unvalidated
        tags, triggers a Haiku validation call (if ``self.api_key`` is set)
        and caches the results.

        Returns ``{"tags": [...], "validated": bool}`` where each tag entry
        has ``tag``, ``valid`` (bool|None), ``reason`` (str|None),
        ``validated`` (bool).
        """
        tag_rows = self.conn.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = ?", (oracle_id,)
        ).fetchall()
        all_tags = [r["tag"] for r in tag_rows]

        if not all_tags:
            return {"tags": [], "validated": False}

        # Check cached validations
        val_rows = self.conn.execute(
            "SELECT tag, valid, reason FROM card_tag_validations WHERE oracle_id = ?",
            (oracle_id,),
        ).fetchall()
        validated = {r["tag"]: {"valid": bool(r["valid"]), "reason": r["reason"]}
                     for r in val_rows}

        unvalidated = [t for t in all_tags if t not in validated]

        # On-demand validation via Haiku
        if unvalidated and self.api_key:
            card_row = self.conn.execute(
                "SELECT oracle_id, name, type_line, oracle_text "
                "FROM cards WHERE oracle_id = ?",
                (oracle_id,),
            ).fetchone()
            if card_row:
                from mtg_collector.services.deck_builder.tag_validator import TagValidator
                validator = TagValidator(self.conn)
                validator._validate_card(dict(card_row))
                # Re-fetch after validation
                val_rows = self.conn.execute(
                    "SELECT tag, valid, reason FROM card_tag_validations "
                    "WHERE oracle_id = ?",
                    (oracle_id,),
                ).fetchall()
                validated = {r["tag"]: {"valid": bool(r["valid"]), "reason": r["reason"]}
                             for r in val_rows}
                unvalidated = [t for t in all_tags if t not in validated]

        tags = []
        for t in sorted(all_tags):
            if t in validated:
                tags.append({"tag": t, "valid": validated[t]["valid"],
                             "reason": validated[t]["reason"], "validated": True})
            else:
                tags.append({"tag": t, "valid": None, "reason": None,
                             "validated": False})

        return {"tags": tags, "validated": len(unvalidated) == 0}

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
        if self._deck_context(deck_id).hypothetical:
            commanders = [c for c in self.deck_repo.get_expected_cards_full(deck_id)
                          if c.get("deck_zone") == "commander"]
        else:
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
            f"SELECT ct.tag FROM card_tags ct WHERE ct.oracle_id = ?"
            f" AND {tag_validation_filter()}", (oracle_id,)
        ).fetchall()
        card_tags = {row["tag"] for row in rows}
        for cat_name, cat_info in INFRASTRUCTURE.items():
            if card_tags & cat_info["tags"]:
                categories.add(cat_name)
        return categories

    @staticmethod
    def _clean_tags(tags: set[str], type_line: str) -> set[str]:
        """Apply hard-coded post-validation tag rules.

        These catch systematic tagging errors that Haiku validation
        doesn't reliably fix.
        """
        type_line = type_line or ""
        if "Creature" not in type_line:
            tags.discard("mana-dork")
        if "Land" in type_line:
            # Lands aren't ramp — they're the baseline mana source.
            # Tags like adds-multiple-mana on dual lands don't mean ramp.
            for t in ("ramp", "mana-rock", "adds-multiple-mana"):
                tags.discard(t)
        return tags

    def _get_card_tags(self, oracle_id: str) -> set:
        """Get all validated tags for a card, with post-validation rules applied."""
        rows = self.conn.execute(
            f"SELECT ct.tag FROM card_tags ct WHERE ct.oracle_id = ?"
            f" AND {tag_validation_filter()}", (oracle_id,)
        ).fetchall()
        tags = {row["tag"] for row in rows}
        card = self.conn.execute(
            "SELECT type_line FROM cards WHERE oracle_id = ?", (oracle_id,)
        ).fetchone()
        return self._clean_tags(tags, card["type_line"] if card else "")

    def _find_best_copy(self, oracle_id: str, deck_id: int) -> Optional[int]:
        """Find the best unassigned owned copy by bling score."""
        avail = self._deck_context(deck_id).availability_sql()
        rows = self.conn.execute(
            f"""SELECT c.id, c.finish, p.frame_effects, p.full_art, p.promo, p.promo_types
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               WHERE p.oracle_id = ?
                 AND c.status = 'owned'
                 {avail}
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
        copies = self._find_basic_land_copies(color, deck_id, 1)
        return copies[0] if copies else None

    def _find_basic_land_copies(self, color: str, deck_id: int, count: int) -> List[int]:
        """Find up to `count` unassigned basic land copies for the given color."""
        land_names = [name for name, c in {**BASIC_LANDS, **SNOW_BASICS}.items() if c == color]
        if not land_names:
            return []
        placeholders = ",".join("?" * len(land_names))
        avail = self._deck_context(deck_id).availability_sql()
        rows = self.conn.execute(
            f"""SELECT c.id
                FROM collection c
                JOIN printings p ON c.printing_id = p.printing_id
                JOIN cards card ON p.oracle_id = card.oracle_id
                WHERE card.name IN ({placeholders})
                  AND c.status = 'owned'
                  {avail}
                LIMIT ?""",
            [*land_names, count],
        ).fetchall()
        return [r["id"] for r in rows]

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
        row = self.conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN card.type_line LIKE '%Land%' THEN 1 ELSE 0 END) AS lands
               FROM collection c
               JOIN printings p ON c.printing_id = p.printing_id
               JOIN cards card ON p.oracle_id = card.oracle_id
               WHERE c.deck_id = ?""",
            (deck_id,),
        ).fetchone()
        categories = {"Lands": row["lands"] or 0}
        # Count cards per infrastructure category via tags
        for cat_name, cat_info in INFRASTRUCTURE.items():
            placeholders = ",".join("?" * len(cat_info["tags"]))
            cat_row = self.conn.execute(
                f"""SELECT COUNT(DISTINCT p.oracle_id) AS cnt
                    FROM collection c
                    JOIN printings p ON c.printing_id = p.printing_id
                    JOIN card_tags ct ON ct.oracle_id = p.oracle_id
                    WHERE c.deck_id = ? AND ct.tag IN ({placeholders})
                      AND {tag_validation_filter()}""",
                [deck_id, *cat_info["tags"]],
            ).fetchone()
            categories[cat_name] = cat_row["cnt"]
        return {"total": row["total"] or 0, "categories": categories}

    def _get_plan_progress(self, deck_id: int, cards: List[dict],
                           plan: Optional[dict],
                           ctx: DeckContext) -> Optional[dict]:
        """Get plan progress by counting cards with matching tags or queries.

        Plan targets are tag names from card_tags, custom SQL queries,
        or the special value "lands" which is counted by type line.
        """
        if not plan or "targets" not in plan:
            return None

        targets = plan["targets"]

        card_from, card_where = ctx.card_source_sql()
        card_from_ext, _ = ctx.card_source_ext_sql()
        count_expr = ctx.count_expr()
        tag_count_expr = ctx.tag_count_expr()

        # Count all tag occurrences + land count in two queries
        tag_rows = self.conn.execute(
            f"""SELECT ct.tag, {tag_count_expr} AS cnt
               {card_from}
               JOIN card_tags ct ON ct.oracle_id = card.oracle_id
               WHERE {card_where} AND {tag_validation_filter()}
               GROUP BY ct.tag""",
            (deck_id,),
        ).fetchall()
        tag_counts = {r["tag"]: r["cnt"] for r in tag_rows}

        land_row = self.conn.execute(
            f"""SELECT {count_expr} AS cnt {card_from}
               WHERE {card_where} AND card.type_line LIKE '%Land%'""",
            (deck_id,),
        ).fetchone()

        progress = {}
        for target_name, target_val in targets.items():
            target_count = target_val["count"]
            if target_val["type"] == "lands":
                current = land_row["cnt"]
            elif target_val["type"] == "query":
                # Use extended join with printings for custom queries that may reference p.*
                cnt_row = self.conn.execute(
                    f"""SELECT {count_expr} AS cnt
                       {card_from_ext}
                       WHERE {card_where} AND ({target_val['query']})""",  # noqa: S608
                    (deck_id,),
                ).fetchone()
                current = cnt_row["cnt"]
            elif target_name in INFRASTRUCTURE:
                # Infrastructure broad category: count distinct oracle_ids
                # matching ANY sub-tag to avoid double-counting.
                sub_tags = INFRASTRUCTURE[target_name]["tags"]
                placeholders = ",".join("?" for _ in sub_tags)
                cnt_row = self.conn.execute(
                    f"""SELECT COUNT(DISTINCT card.oracle_id) AS cnt
                       {card_from}
                       JOIN card_tags ct ON ct.oracle_id = card.oracle_id
                       WHERE {card_where}
                         AND ct.tag IN ({placeholders})
                         AND {tag_validation_filter()}""",
                    (deck_id, *sorted(sub_tags)),
                ).fetchone()
                current = cnt_row["cnt"]
            else:
                current = tag_counts.get(target_name, 0)
            entry = {"current": current, "target": target_count, "label": target_val["label"]}
            progress[target_name] = entry
        return progress

    def _tag_coverage(self, deck_id: int, ctx: DeckContext) -> tuple:
        """Compute tag coverage stats for nonland cards in a deck.

        Returns (coverage_pct, avg_roles, zero_role_card_names).
        """
        card_from, card_where = ctx.card_source_sql()
        rows = self.conn.execute(
            f"""SELECT card.name, COUNT(ct.tag) AS role_count
               {card_from}
               LEFT JOIN card_tags ct ON ct.oracle_id = card.oracle_id
                 AND {tag_validation_filter()}
               WHERE {card_where} AND card.type_line NOT LIKE '%Land%'
               GROUP BY card.oracle_id""",
            (deck_id,),
        ).fetchall()
        if not rows:
            return 0.0, 0.0, []

        n_cards = len(rows)
        total_roles = sum(r["role_count"] for r in rows)
        covered = sum(1 for r in rows if r["role_count"] > 0)
        zero_role = [r["name"] for r in rows if r["role_count"] == 0]

        coverage = round(covered / n_cards * 100, 1)
        avg_roles = round(total_roles / n_cards, 1)
        return coverage, avg_roles, zero_role

    def _suggest_utility_lands(self, deck_id: int, commander_ci: Set[str]) -> List[dict]:
        """Find owned unassigned nonbasic lands in commander CI, sorted by EDHREC rank."""
        ctx = self._deck_context(deck_id)
        ci_clauses = self._ci_exclusion_sql(commander_ci)
        avail = ctx.availability_sql()
        exclude_sql, exclude_params = ctx.exclude_deck_sql(deck_id)
        rows = self.conn.execute(
            f"""SELECT card.name, p.set_code,
                       json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank
                FROM collection c
                JOIN printings p ON c.printing_id = p.printing_id
                JOIN cards card ON p.oracle_id = card.oracle_id
                WHERE c.status = 'owned'
                  {avail}
                  AND card.type_line LIKE '%Land%'
                  AND card.type_line NOT LIKE '%Basic%'
                  {exclude_sql}
                  {ci_clauses}
                GROUP BY card.oracle_id
                ORDER BY edhrec_rank ASC NULLS LAST
                LIMIT 10""",
            exclude_params,
        ).fetchall()
        return [dict(r) for r in rows]

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

    # ── Replacements ────────────────────────────────────────────

    def get_replacements(self, deck_id: int, collection_id: int = None,
                         oracle_id: str = None) -> dict:
        """Get replacement candidates for a card in a deck.

        For physical decks, pass collection_id. For hypothetical, pass oracle_id.
        Returns role-based and type-based suggestions from owned collection.
        """
        ctx = self._deck_context(deck_id)

        # Find the card being replaced
        if ctx.hypothetical:
            if not oracle_id:
                raise ValueError("oracle_id is required for hypothetical decks")
            deck_cards = self.deck_repo.get_expected_cards_full(deck_id)
            card = None
            for c in deck_cards:
                if c["oracle_id"] == oracle_id:
                    card = c
                    break
            if not card:
                raise ValueError(f"Card {oracle_id} not in deck {deck_id}")
        else:
            deck_cards = self.deck_repo.get_cards(deck_id)
            card = None
            for c in deck_cards:
                if c["id"] == collection_id:
                    card = c
                    break
            if not card:
                raise ValueError(f"Collection entry {collection_id} not in deck {deck_id}")

        commander_ci = self._get_commander_identity(deck_id)
        ci_clauses = self._ci_exclusion_sql(commander_ci) if commander_ci else ""

        # Build exclude set: all oracle_ids already in the deck
        exclude_oids = {c["oracle_id"] for c in deck_cards}
        exclude_list = ",".join(f"'{oid}'" for oid in exclude_oids) if exclude_oids else "''"

        # Get the card's plan-relevant tags (regular tags + custom queries)
        plan = self.get_plan(deck_id)
        targets = plan["targets"] if plan and "targets" in plan else {}
        plan_tag_keys = {k for k, v in targets.items() if v["type"] == "tag"}
        card_tags = self._get_card_tags(card["oracle_id"])
        card_plan_tags = card_tags & plan_tag_keys

        # Check which custom query targets this card matches
        card_custom_queries: list[dict] = []
        for key, val in targets.items():
            if val["type"] == "query":
                match = self.conn.execute(
                    f"SELECT 1 FROM cards card "  # noqa: S608
                    f"JOIN printings p ON p.oracle_id = card.oracle_id "
                    f"WHERE card.oracle_id = ? AND ({val['query']})",
                    (card["oracle_id"],),
                ).fetchone()
                if match:
                    card_custom_queries.append(val)

        target_cmc = int(card.get("cmc") or 0)

        # Role-based suggestions: from tag matches + custom query matches
        role_suggestions = self._query_role_replacements(
            deck_id, target_cmc, ci_clauses, exclude_list, card_plan_tags=card_plan_tags,
        )
        for cq in card_custom_queries:
            cq_results = self._query_role_replacements(
                deck_id, target_cmc, ci_clauses, exclude_list, custom_where=cq["query"],
            )
            # Merge without duplicates
            seen = {r["oracle_id"] for r in role_suggestions}
            for r in cq_results:
                if r["oracle_id"] not in seen:
                    role_suggestions.append(r)
                    seen.add(r["oracle_id"])

        # Type-based suggestions
        type_suggestions = self._query_type_replacements(
            deck_id, card, target_cmc, ci_clauses, exclude_list,
        )

        all_labels = sorted(card_plan_tags) + [cq["label"] for cq in card_custom_queries]
        card_info = {
            "name": card["name"],
            "cmc": card.get("cmc"),
            "tags": all_labels,
            "type_line": card.get("type_line", ""),
            "mana_cost": card.get("mana_cost", ""),
            "colors": card.get("colors", "[]"),
            "set_code": card.get("set_code", ""),
            "collector_number": card.get("collector_number", ""),
        }
        return {
            "card": card_info,
            "role_suggestions": role_suggestions,
            "type_suggestions": type_suggestions,
        }

    def _query_role_replacements(self, deck_id: int, target_cmc: int,
                                  ci_clauses: str, exclude_list: str,
                                  *, card_plan_tags: set | None = None,
                                  custom_where: str | None = None) -> list:
        """Find replacement candidates by plan tags or custom query at same CMC."""
        if card_plan_tags:
            tags = sorted(card_plan_tags)
            tag_placeholders = ",".join("?" for _ in tags)
            tag_join = (f"JOIN card_tags ct ON ct.oracle_id = card.oracle_id"
                        f"\n                  AND ct.tag IN ({tag_placeholders})"
                        f"\n                  AND {tag_validation_filter('ct')}")
            order = "ORDER BY COUNT(DISTINCT ct.tag) DESC"
            params = (*tags, target_cmc)
        elif custom_where:
            tag_join = ""
            order = ""
            params = (target_cmc,)
        else:
            return []

        custom_clause = f"AND ({custom_where})" if custom_where else ""
        avail = self._deck_context(deck_id).availability_sql()

        rows = self.conn.execute(
            f"""SELECT card.oracle_id, card.name, card.type_line,
                       card.mana_cost, card.cmc,
                       p.set_code, p.collector_number, p.image_uri, p.rarity,
                       MIN(c.id) AS collection_id,
                       GROUP_CONCAT(DISTINCT ct2.tag) AS tags
                FROM cards card
                JOIN printings p ON p.oracle_id = card.oracle_id
                JOIN collection c ON c.printing_id = p.printing_id
                {tag_join}
                LEFT JOIN card_tags ct2 ON ct2.oracle_id = card.oracle_id
                  AND {tag_validation_filter("ct2")}
                WHERE c.status = 'owned'
                  {avail}
                  AND card.oracle_id NOT IN ({exclude_list})
                  AND CAST(card.cmc AS INTEGER) = ?
                  {ci_clauses}
                  {custom_clause}
                GROUP BY card.oracle_id
                {order}
                LIMIT 20""",  # noqa: S608
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def _query_type_replacements(self, deck_id: int, card: dict, target_cmc: int,
                                  ci_clauses: str, exclude_list: str) -> list:
        """Find replacement candidates matching type, CMC, color, and P/T."""
        type_line = card.get("type_line", "")
        # Extract primary supertype
        supertype = None
        for st in ["Creature", "Artifact", "Enchantment", "Instant",
                    "Sorcery", "Planeswalker"]:
            if st in type_line:
                supertype = st
                break
        if not supertype:
            return []

        target_colors = card.get("colors", "[]")
        # Ensure colors is a JSON string for exact match
        if isinstance(target_colors, list):
            target_colors = json.dumps(target_colors)

        params: list = [target_cmc, target_colors]
        pt_clause = ""
        if supertype == "Creature":
            # Try to get P/T from the card's raw_json via a quick lookup
            row = self.conn.execute(
                """SELECT json_extract(p.raw_json, '$.power') AS power,
                          json_extract(p.raw_json, '$.toughness') AS toughness
                   FROM printings p WHERE p.oracle_id = ? LIMIT 1""",
                (card["oracle_id"],),
            ).fetchone()
            if row and row["power"] is not None:
                pt_clause = (" AND json_extract(p.raw_json, '$.power') = ?"
                             " AND json_extract(p.raw_json, '$.toughness') = ?")
                params.extend([row["power"], row["toughness"]])

        avail = self._deck_context(deck_id).availability_sql()
        rows = self.conn.execute(
            f"""SELECT card.oracle_id, card.name, card.type_line,
                       card.mana_cost, card.cmc, card.colors,
                       p.set_code, p.collector_number, p.image_uri, p.rarity,
                       json_extract(p.raw_json, '$.power') AS power,
                       json_extract(p.raw_json, '$.toughness') AS toughness,
                       MIN(c.id) AS collection_id
                FROM cards card
                JOIN printings p ON p.oracle_id = card.oracle_id
                JOIN collection c ON c.printing_id = p.printing_id
                WHERE c.status = 'owned'
                  {avail}
                  AND card.oracle_id NOT IN ({exclude_list})
                  AND CAST(card.cmc AS INTEGER) = ?
                  AND card.colors = ?
                  AND card.type_line LIKE '%' || '{supertype}' || '%'
                  {pt_clause}
                  {ci_clauses}
                GROUP BY card.oracle_id
                LIMIT 20""",  # noqa: S608
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]

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

            for group_name, group_cards, limits in [
                ("Creature", creatures, CREATURE_CURVE_LIMITS),
                ("Noncreature", noncreatures, NONCREATURE_CURVE_LIMITS),
            ]:
                group_curve = {}
                for c in group_cards:
                    cmc = int(c.get("cmc", 0) or 0)
                    bucket = min(cmc, 7)
                    group_curve[bucket] = group_curve.get(bucket, 0) + 1
                for bucket, (lo, hi) in limits.items():
                    cnt = group_curve.get(bucket, 0)
                    if cnt < lo or cnt > hi:
                        label = f"{bucket}+" if bucket == 7 else str(bucket)
                        steps.append(f"Curve: {group_name} CMC {label} has {cnt} (target {lo}-{hi})")

            steps.append("Ready for final validation and description")

        return steps
