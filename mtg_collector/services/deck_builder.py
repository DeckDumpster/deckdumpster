"""Commander deck building service using Command Zone 2025 template."""

import json
import re
import sqlite3

from mtg_collector.db.models import Deck, DeckRepository


class RoleClassifier:
    """Classifies cards by role using oracle_text regex patterns."""

    # Priority order — first match wins for primary role
    ROLE_PATTERNS = [
        ("Ramp", [
            r"add \{",
            r"add .* mana",
            r"search your library for a.*land.*onto the battlefield",
        ]),
        ("Card Advantage", [
            r"draw a card",
            r"draw .* cards",
            r"draws a card",
            r"look at the top .* cards",
            r"exile .* you may play",
        ]),
        ("Targeted Disruption", [
            r"destroy target",
            r"exile target",
            r"deals? \d+ damage to (?:target|any)",
            r"return target .* to .* owner's hand",
            r"counter target",
        ]),
        ("Mass Disruption", [
            r"destroy all",
            r"exile all",
            r"all creatures get -",
            r"each creature gets -",
            r"each opponent.*sacrifice",
        ]),
    ]

    def classify(self, card: dict) -> list[str]:
        """Return all matching roles for a card. Lands detected by type_line."""
        roles = []
        type_line = (card.get("type_line") or "").lower()

        if "land" in type_line and "creature" not in type_line:
            roles.append("Lands")

        oracle = (card.get("oracle_text") or "").lower()
        for role_name, patterns in self.ROLE_PATTERNS:
            for pat in patterns:
                if re.search(pat, oracle):
                    roles.append(role_name)
                    break

        if not roles:
            roles.append("Plan Cards")

        return roles

    def primary_role(self, card: dict) -> str:
        """Return the first (highest priority) matching role."""
        return self.classify(card)[0]


class DeckTemplate:
    """Command Zone 2025 template with target counts."""

    TARGETS = {
        "Lands": 38,
        "Ramp": 10,
        "Card Advantage": 12,
        "Targeted Disruption": 12,
        "Mass Disruption": 6,
        "Plan Cards": 30,
    }

    # Canonical display order
    ORDER = ["Lands", "Ramp", "Card Advantage", "Targeted Disruption",
             "Mass Disruption", "Plan Cards"]

    def compare(self, current: dict[str, int]) -> dict[str, dict]:
        """Compare current role counts against targets. Returns per-role status."""
        result = {}
        for role in self.ORDER:
            target = self.TARGETS[role]
            have = current.get(role, 0)
            gap = target - have
            if gap > 0:
                status = f"NEED {gap} MORE"
            elif gap == 0:
                status = "COMPLETE"
            else:
                status = f"{-gap} OVER"
            result[role] = {"have": have, "target": target, "gap": gap, "status": status}
        return result


class DeckBuilderService:
    """Orchestrates commander deck building operations."""

    BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest",
                        "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
                        "Snow-Covered Swamp", "Snow-Covered Mountain",
                        "Snow-Covered Forest"}

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.repo = DeckRepository(conn)
        self.classifier = RoleClassifier()
        self.template = DeckTemplate()

    def find_commanders(self, query: str) -> list[dict]:
        """Search owned legendary creatures matching query, deduplicated by oracle_id."""
        rows = self.conn.execute(
            """SELECT c.oracle_id, c.name, c.mana_cost, c.color_identity,
                      c.oracle_text, c.type_line, c.cmc,
                      p.printing_id, p.image_uri, p.set_code, p.collector_number
               FROM cards c
               JOIN printings p ON p.oracle_id = c.oracle_id
               JOIN collection col ON col.printing_id = p.printing_id
               WHERE ((c.type_line LIKE '%Legendary%' AND c.type_line LIKE '%Creature%')
                  OR c.oracle_text LIKE '%can be your commander%')
               AND c.name LIKE ?
               AND col.status = 'owned'
               ORDER BY c.name
               LIMIT 50""",
            (f"%{query}%",),
        ).fetchall()
        seen = set()
        results = []
        for r in rows:
            if r["oracle_id"] not in seen:
                seen.add(r["oracle_id"])
                results.append(dict(r))
            if len(results) >= 20:
                break
        return results

    def create_deck(self, oracle_id: str) -> dict:
        """Create a hypothetical commander deck for the given commander."""
        card = self.conn.execute(
            "SELECT oracle_id, name, color_identity FROM cards WHERE oracle_id = ?",
            (oracle_id,),
        ).fetchone()
        if not card:
            raise ValueError(f"Card not found: {oracle_id}")

        # Pre-populate template role categories
        template_categories = [
            {"name": role, "target": target, "cards": []}
            for role, target in DeckTemplate.TARGETS.items()
        ]
        deck = Deck(
            id=None,
            name=card["name"],
            format="commander",
            hypothetical=True,
            commander_oracle_id=oracle_id,
            sub_plans=json.dumps(template_categories),
        )
        deck_id = self.repo.add(deck)
        self.conn.commit()
        return {"deck_id": deck_id, "name": card["name"],
                "color_identity": card["color_identity"]}

    def save_plan(self, deck_id: int, plan: str) -> None:
        """Save the deck plan/theme."""
        self.repo.update(deck_id, {"plan": plan})
        self.conn.commit()

    def save_sub_plans(self, deck_id: int, sub_plans: list[dict]) -> None:
        """Save sub-plan categories. Each dict: {name, target, cards: []}.

        Merges with existing template role categories (Lands, Ramp, etc.)
        which are pre-populated at deck creation.
        """
        deck = self.repo.get(deck_id)
        existing = json.loads(deck["sub_plans"]) if deck and deck.get("sub_plans") else []

        # Keep existing template roles, replace custom sub-plans
        template_names = set(DeckTemplate.TARGETS.keys())
        template_entries = [e for e in existing if e["name"] in template_names]

        for sp in sub_plans:
            sp.setdefault("cards", [])

        merged = template_entries + sub_plans
        self.repo.update(deck_id, {"sub_plans": json.dumps(merged)})
        self.conn.commit()

    def assign_categories(self, deck_id: int, collection_id: int,
                          category_names: list[str]) -> list[str]:
        """Assign a card to template roles and/or sub-plan categories. Returns matched names."""
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")
        sub_plans_raw = deck.get("sub_plans")
        if not sub_plans_raw:
            raise ValueError("No categories defined for this deck")

        sub_plans = json.loads(sub_plans_raw)
        matched = []
        for sp in sub_plans:
            if sp["name"] in category_names:
                cards = sp.setdefault("cards", [])
                if collection_id not in cards:
                    cards.append(collection_id)
                matched.append(sp["name"])

        unknown = set(category_names) - set(matched)
        if unknown:
            raise ValueError(f"Unknown category(s): {', '.join(unknown)}")

        self.repo.update(deck_id, {"sub_plans": json.dumps(sub_plans)})
        self.conn.commit()
        return matched

    def _get_cards_with_text(self, deck_id: int) -> list[dict]:
        """Get deck cards including oracle_text (needed for role classification)."""
        rows = self.conn.execute(
            """SELECT col.id, col.printing_id, col.finish, col.deck_zone,
                      p.set_code, p.collector_number, p.rarity, p.image_uri,
                      c.name, c.type_line, c.mana_cost, c.cmc,
                      c.colors, c.color_identity, c.oracle_text, p.oracle_id
               FROM collection col
               JOIN printings p ON col.printing_id = p.printing_id
               JOIN cards c ON p.oracle_id = c.oracle_id
               WHERE col.deck_id = ?
               ORDER BY c.name""",
            (deck_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def audit(self, deck_id: int) -> dict:
        """Full deck audit: role distribution, mana curve, EDHREC recs."""
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        cards = self._get_cards_with_text(deck_id)

        # Commander info
        cmd_name = None
        cmd_ci = []
        if deck["commander_oracle_id"]:
            cmd_row = self.conn.execute(
                "SELECT name, color_identity FROM cards WHERE oracle_id = ?",
                (deck["commander_oracle_id"],),
            ).fetchone()
            if cmd_row:
                cmd_name = cmd_row["name"]
                ci_raw = cmd_row["color_identity"]
                cmd_ci = json.loads(ci_raw) if isinstance(ci_raw, str) and ci_raw else []

        # Count nonland cards and build mana curve
        nonland_count = 0
        curve: dict[int, int] = {}
        for card in cards:
            type_line = (card.get("type_line") or "").lower()
            if "land" in type_line and "creature" not in type_line:
                continue
            nonland_count += 1
            cmc = int(card.get("cmc") or 0)
            bucket = min(cmc, 7)  # 7+ grouped
            curve[bucket] = curve.get(bucket, 0) + 1

        # EDHREC recommendations (if table exists)
        edhrec_recs = []
        if deck["commander_oracle_id"]:
            edhrec_recs = self._get_edhrec_recs(deck_id, deck["commander_oracle_id"])

        # Category tracking (template roles + sub-plans, all explicit assignments)
        template_status = {}
        sub_plan_status = []
        cards_by_id = {c["id"]: c for c in cards}
        sub_plans_raw = deck.get("sub_plans")
        template_names = set(DeckTemplate.TARGETS.keys())

        if sub_plans_raw:
            all_categories = json.loads(sub_plans_raw)
            for cat in all_categories:
                assigned_ids = cat.get("cards", [])
                matched_names = [cards_by_id[cid]["name"]
                                 for cid in assigned_ids if cid in cards_by_id]
                count = len(matched_names)
                target = cat.get("target", 0)
                gap = target - count
                if gap > 0:
                    status = f"NEED {gap} MORE"
                elif gap == 0:
                    status = "COMPLETE"
                else:
                    status = f"{-gap} OVER"
                entry = {
                    "name": cat["name"],
                    "target": target,
                    "have": count,
                    "gap": gap,
                    "status": status,
                    "matched": matched_names,
                }
                if cat["name"] in template_names:
                    template_status[cat["name"]] = entry
                else:
                    sub_plan_status.append(entry)

        # Ensure all template roles appear even if not in sub_plans
        for role in DeckTemplate.ORDER:
            if role not in template_status:
                target = DeckTemplate.TARGETS[role]
                template_status[role] = {
                    "name": role, "target": target, "have": 0,
                    "gap": target, "status": f"NEED {target} MORE",
                    "matched": [],
                }

        # Ordered template comparison
        template_comparison = {role: template_status[role] for role in DeckTemplate.ORDER}

        # Find biggest gap for next priority (non-land roles only —
        # lands use a separate workflow via mana-analysis + add-basics)
        biggest_gap_role = None
        biggest_gap = 0
        non_land_roles = [r for r in DeckTemplate.ORDER if r != "Lands"]
        for role in non_land_roles:
            info = template_comparison[role]
            if info["gap"] > biggest_gap:
                biggest_gap = info["gap"]
                biggest_gap_role = role

        return {
            "deck_id": deck_id,
            "name": deck.get("name"),
            "plan": deck.get("plan"),
            "commander": cmd_name,
            "color_identity": cmd_ci,
            "card_count": len(cards),
            "nonland_count": nonland_count,
            "template": template_comparison,
            "sub_plans": sub_plan_status,
            "curve": curve,
            "edhrec": edhrec_recs,
            "next_priority": biggest_gap_role,
            "next_priority_gap": biggest_gap,
        }

    def _get_edhrec_recs(self, deck_id: int, commander_oracle_id: str) -> list[dict]:
        """Get EDHREC recommendations that are owned but not in this deck."""
        # Check if table exists
        table_check = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edhrec_recommendations'"
        ).fetchone()
        if not table_check:
            return []

        in_deck_oracle = {c["oracle_id"] for c in self.repo.get_cards(deck_id)
                          if c.get("oracle_id")}

        rows = self.conn.execute(
            """SELECT er.card_oracle_id, er.inclusion_rate, er.synergy_score, er.rank,
                      c.name, col.id as collection_id
               FROM edhrec_recommendations er
               JOIN cards c ON er.card_oracle_id = c.oracle_id
               JOIN printings p ON p.oracle_id = c.oracle_id
               JOIN collection col ON col.printing_id = p.printing_id
               WHERE er.commander_oracle_id = ?
                 AND col.status = 'owned'
               ORDER BY er.inclusion_rate DESC
               LIMIT 50""",
            (commander_oracle_id,),
        ).fetchall()

        results = []
        seen = set()
        for r in rows:
            oid = r["card_oracle_id"]
            if oid in in_deck_oracle or oid in seen:
                continue
            seen.add(oid)
            results.append(dict(r))
            if len(results) >= 20:
                break
        return results

    def find_basic_land(self, deck_id: int, name: str) -> int | None:
        """Find an unassigned basic land by exact name. Returns collection_id or None."""
        row = self.conn.execute(
            """SELECT col.id FROM collection col
               JOIN printings p ON col.printing_id = p.printing_id
               JOIN cards c ON p.oracle_id = c.oracle_id
               WHERE c.name = ? AND col.status = 'owned' AND col.deck_id IS NULL
               LIMIT 1""",
            (name,),
        ).fetchone()
        return row["id"] if row else None

    def search(self, deck_id: int, query: str, role: str = None,
               card_type: str = None, max_cmc: int = None) -> list[dict]:
        """Search owned cards matching commander color identity, not already in deck."""
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        # Commander color identity
        cmd_colors = []
        if deck["commander_oracle_id"]:
            row = self.conn.execute(
                "SELECT color_identity FROM cards WHERE oracle_id = ?",
                (deck["commander_oracle_id"],),
            ).fetchone()
            if row and row["color_identity"]:
                ci_raw = row["color_identity"]
                cmd_colors = json.loads(ci_raw) if isinstance(ci_raw, str) else ci_raw

        # Cards already in deck (by oracle_id for singleton check)
        in_deck_oracle = {c["oracle_id"] for c in self.repo.get_cards(deck_id)
                          if c.get("oracle_id")}

        search = f"%{query}%"
        # Hypothetical: search all owned cards regardless of assignment
        rows = self.conn.execute(
            """SELECT col.id, col.printing_id, col.finish, col.condition,
                      p.set_code, p.collector_number, p.rarity, p.image_uri,
                      p.frame_effects, p.border_color, p.full_art, p.promo, p.promo_types,
                      c.name, c.type_line, c.mana_cost, c.cmc,
                      c.color_identity, c.oracle_id, c.oracle_text
               FROM collection col
               JOIN printings p ON col.printing_id = p.printing_id
               JOIN cards c ON p.oracle_id = c.oracle_id
               WHERE col.status = 'owned'
                 AND (c.name LIKE ? OR c.type_line LIKE ? OR c.oracle_text LIKE ?)
               ORDER BY c.name
               LIMIT 200""",
            (search, search, search),
        ).fetchall()

        # EDHREC data lookup
        edhrec_map = {}
        table_check = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edhrec_recommendations'"
        ).fetchone()
        if table_check and deck["commander_oracle_id"]:
            erecs = self.conn.execute(
                "SELECT card_oracle_id, inclusion_rate, synergy_score FROM edhrec_recommendations WHERE commander_oracle_id = ?",
                (deck["commander_oracle_id"],),
            ).fetchall()
            edhrec_map = {r["card_oracle_id"]: dict(r) for r in erecs}

        results = []
        seen_oracle = set()
        for r in rows:
            card = dict(r)
            oid = card["oracle_id"]

            is_basic = card.get("name", "") in self.BASIC_LAND_NAMES

            # Skip cards already in deck (singleton rule, basics exempt)
            if oid in in_deck_oracle and not is_basic:
                continue

            # Skip duplicates (same oracle_id, different printing; basics exempt)
            if oid in seen_oracle and not is_basic:
                continue

            # Color identity filter
            card_ci = json.loads(card["color_identity"]) if isinstance(card["color_identity"], str) and card["color_identity"] else []
            if card_ci and cmd_colors:
                if not set(card_ci).issubset(set(cmd_colors)):
                    continue

            # Optional filters
            if card_type:
                if card_type.lower() not in (card.get("type_line") or "").lower():
                    continue
            if max_cmc is not None:
                if (card.get("cmc") or 0) > max_cmc:
                    continue

            # Classify roles
            card["roles"] = self.classifier.classify(card)
            card["primary_role"] = card["roles"][0]

            # Optional role filter
            if role and role not in card["roles"]:
                continue

            # Attach EDHREC data if available
            erec = edhrec_map.get(oid)
            if erec:
                card["edhrec_rate"] = erec.get("inclusion_rate")
                card["edhrec_synergy"] = erec.get("synergy_score")

            seen_oracle.add(oid)
            results.append(card)
            if len(results) >= 50:
                break

        return results

    def add_card(self, deck_id: int, collection_id: int,
                 categories: list[str] | None = None) -> dict:
        """Add a card to the deck. Validates singleton and color identity."""
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        # Get the card info
        card_row = self.conn.execute(
            """SELECT col.id, p.set_code, p.collector_number,
                      c.name, c.type_line, c.oracle_id, c.color_identity, c.oracle_text
               FROM collection col
               JOIN printings p ON col.printing_id = p.printing_id
               JOIN cards c ON p.oracle_id = c.oracle_id
               WHERE col.id = ?""",
            (collection_id,),
        ).fetchone()
        if not card_row:
            raise ValueError(f"Collection entry not found: {collection_id}")

        card = dict(card_row)

        # Singleton check (basic lands exempt)
        if card["name"] not in self.BASIC_LAND_NAMES:
            existing = self.conn.execute(
                """SELECT col.id FROM collection col
                   JOIN printings p ON col.printing_id = p.printing_id
                   JOIN cards c ON p.oracle_id = c.oracle_id
                   WHERE col.deck_id = ? AND c.oracle_id = ?""",
                (deck_id, card["oracle_id"]),
            ).fetchone()
            if existing:
                raise ValueError(f"Singleton violation: {card['name']} is already in the deck")

        # Color identity check
        if deck["commander_oracle_id"]:
            cmd_row = self.conn.execute(
                "SELECT color_identity FROM cards WHERE oracle_id = ?",
                (deck["commander_oracle_id"],),
            ).fetchone()
            if cmd_row:
                cmd_ci = json.loads(cmd_row["color_identity"]) if isinstance(cmd_row["color_identity"], str) and cmd_row["color_identity"] else []
                card_ci = json.loads(card["color_identity"]) if isinstance(card["color_identity"], str) and card["color_identity"] else []
                if card_ci and cmd_ci:
                    if not set(card_ci).issubset(set(cmd_ci)):
                        raise ValueError(
                            f"Color identity violation: {card['name']} ({card_ci}) "
                            f"not within commander identity ({cmd_ci})"
                        )

        # Add card — hypothetical decks skip assignment conflict check
        if deck["hypothetical"]:
            self.conn.execute(
                "UPDATE collection SET deck_id = ?, deck_zone = 'mainboard' WHERE id = ?",
                (deck_id, collection_id),
            )
        else:
            self.repo.add_cards(deck_id, [collection_id], "mainboard")
        self.conn.commit()

        # Assign to categories (template roles and/or sub-plans)
        assigned_categories = []
        if categories:
            assigned_categories = self.assign_categories(
                deck_id, collection_id, categories)

        # Get updated count
        count = self.conn.execute(
            "SELECT COUNT(*) FROM collection WHERE deck_id = ?", (deck_id,)
        ).fetchone()[0]

        roles = self.classifier.classify(card)

        # Run abbreviated audit for immediate feedback
        audit = self.audit(deck_id)

        return {
            "name": card["name"],
            "collection_id": collection_id,
            "roles": roles,
            "primary_role": roles[0],
            "deck_card_count": count,
            "categories": assigned_categories,
            "audit": audit,
        }
