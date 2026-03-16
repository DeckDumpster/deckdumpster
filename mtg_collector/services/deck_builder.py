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

    def browse_commanders(self, filters: dict) -> list[dict]:
        """Browse owned legendary creatures with rich filtering.

        Filters: colors, colors_min, colors_max, cmc_max, set_before, set_after,
                 type, text, name, sort (name|cmc|set-date|colors), limit.
        """
        conditions = [
            "col.status = 'owned'",
            "((c.type_line LIKE '%Legendary%' AND c.type_line LIKE '%Creature%')"
            " OR c.oracle_text LIKE '%can be your commander%')",
        ]
        params = []

        if filters.get("colors"):
            color_order = "WUBRG"
            target = sorted([c for c in filters["colors"].upper() if c in color_order],
                            key=lambda c: color_order.index(c))
            conditions.append("c.color_identity = ?")
            params.append(json.dumps(target))

        if filters.get("colors_min") is not None:
            conditions.append("json_array_length(c.color_identity) >= ?")
            params.append(int(filters["colors_min"]))

        if filters.get("colors_max") is not None:
            conditions.append("json_array_length(c.color_identity) <= ?")
            params.append(int(filters["colors_max"]))

        if filters.get("cmc_max") is not None:
            conditions.append("c.cmc <= ?")
            params.append(int(filters["cmc_max"]))

        if filters.get("set_before"):
            conditions.append("s.released_at < ?")
            params.append(f"{filters['set_before']}-01-01")

        if filters.get("set_after"):
            conditions.append("s.released_at >= ?")
            params.append(f"{filters['set_after']}-01-01")

        if filters.get("type"):
            conditions.append("c.type_line LIKE ?")
            params.append(f"%{filters['type']}%")

        if filters.get("text"):
            conditions.append("c.oracle_text LIKE ?")
            params.append(f"%{filters['text']}%")

        if filters.get("name"):
            conditions.append("c.name LIKE ?")
            params.append(f"%{filters['name']}%")

        sort_map = {
            "name": "c.name",
            "cmc": "c.cmc, c.name",
            "set-date": "MIN(s.released_at), c.name",
            "colors": "json_array_length(c.color_identity) DESC, c.name",
        }
        order_by = sort_map.get(filters.get("sort", "name"), "c.name")
        limit = int(filters.get("limit", 25))

        where = " AND ".join(conditions)
        sql = f"""
            SELECT c.oracle_id, c.name, c.mana_cost, c.color_identity,
                   c.oracle_text, c.type_line, c.cmc,
                   MIN(s.released_at) AS first_printed,
                   MIN(s.set_name) AS first_set,
                   GROUP_CONCAT(DISTINCT s.set_name) AS all_sets,
                   COUNT(DISTINCT col.id) AS copies
            FROM cards c
            JOIN printings p ON p.oracle_id = c.oracle_id
            JOIN collection col ON col.printing_id = p.printing_id
            JOIN sets s ON s.set_code = p.set_code
            WHERE {where}
            GROUP BY c.oracle_id
            ORDER BY {order_by}
            LIMIT ?
        """
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def sql_search(self, deck_id: int, where_clause: str) -> list[dict]:
        """Search owned cards using a raw SQL WHERE clause.

        Validates safety (no semicolons, no ATTACH/DETACH/PRAGMA).
        Filters by commander color identity, excludes cards already in deck,
        deduplicates by oracle_id (basics exempt), attaches role + EDHREC data.
        """
        if ";" in where_clause:
            raise ValueError("Semicolons are not allowed in WHERE clauses.")
        if re.search(r"\b(ATTACH|DETACH|PRAGMA)\b", where_clause, re.IGNORECASE):
            raise ValueError("Only read-only WHERE clauses are allowed.")

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

        # Cards already in deck
        in_deck_oracle = {c["oracle_id"] for c in self.repo.get_cards(deck_id)
                          if c.get("oracle_id")}

        # EDHREC data
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

        sql = f"""SELECT col.id, col.printing_id, col.finish, col.condition,
                         p.set_code, p.collector_number, p.rarity, p.image_uri,
                         p.frame_effects, p.border_color, p.full_art, p.promo, p.promo_types,
                         c.name, c.type_line, c.mana_cost, c.cmc,
                         c.color_identity, c.oracle_id, c.oracle_text
                  FROM collection col
                  JOIN printings p ON col.printing_id = p.printing_id
                  JOIN cards c ON p.oracle_id = c.oracle_id
                  WHERE col.status = 'owned'
                    AND ({where_clause})
                  ORDER BY c.cmc, c.name
                  LIMIT 200"""

        rows = self.conn.execute(sql).fetchall()

        results = []
        seen_oracle = set()
        for r in rows:
            card = dict(r)
            oid = card["oracle_id"]
            is_basic = card.get("name", "") in self.BASIC_LAND_NAMES

            if oid in in_deck_oracle and not is_basic:
                continue
            if oid in seen_oracle and not is_basic:
                continue

            card_ci = json.loads(card["color_identity"]) if isinstance(card["color_identity"], str) and card["color_identity"] else []
            if card_ci and cmd_colors:
                if not set(card_ci).issubset(set(cmd_colors)):
                    continue

            card["roles"] = self.classifier.classify(card)
            erec = edhrec_map.get(oid)
            if erec:
                card["edhrec_rate"] = erec.get("inclusion_rate")
                card["edhrec_synergy"] = erec.get("synergy_score")

            seen_oracle.add(oid)
            results.append(card)
            if len(results) >= 50:
                break

        return results

    def add_basics(self, deck_id: int, counts: dict[str, int]) -> dict:
        """Add basic lands to a deck.

        counts: {"Plains": N, "Island": N, ...}
        Returns summary of what was added.
        """
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        preferred_set = deck.get("origin_set_code")
        existing = {r["id"] for r in self.conn.execute(
            "SELECT id FROM collection WHERE deck_id = ?", (deck_id,)).fetchall()}

        results = {}
        total_added = 0

        for name, count in counts.items():
            rows = self.conn.execute("""
                SELECT col.id, p.set_code, p.full_art
                FROM collection col
                JOIN printings p ON col.printing_id = p.printing_id
                JOIN cards c ON p.oracle_id = c.oracle_id
                WHERE c.name = ? AND col.status = 'owned'
                  AND col.id NOT IN (SELECT id FROM collection WHERE deck_id IS NOT NULL)
                ORDER BY
                  p.full_art DESC,
                  CASE WHEN p.set_code = ? THEN 0 ELSE 1 END,
                  col.id
            """, (name, preferred_set)).fetchall()

            if len(rows) < count:
                rows = self.conn.execute("""
                    SELECT col.id, p.set_code, p.full_art
                    FROM collection col
                    JOIN printings p ON col.printing_id = p.printing_id
                    JOIN cards c ON p.oracle_id = c.oracle_id
                    WHERE c.name = ? AND col.status = 'owned'
                      AND col.id NOT IN (SELECT id FROM collection WHERE deck_id = ?)
                    ORDER BY
                      p.full_art DESC,
                      CASE WHEN p.set_code = ? THEN 0 ELSE 1 END,
                      col.id
                """, (name, deck_id, preferred_set)).fetchall()

            added = 0
            full_art_count = 0
            for row in rows:
                if added >= count:
                    break
                if row["id"] in existing:
                    continue
                try:
                    self.add_card(deck_id, row["id"], ["Lands"])
                    existing.add(row["id"])
                    added += 1
                    if row["full_art"]:
                        full_art_count += 1
                except ValueError:
                    continue

            total_added += added
            results[name] = {"requested": count, "added": added,
                             "full_art": full_art_count}

        card_count = self.conn.execute(
            "SELECT COUNT(*) FROM collection WHERE deck_id = ?", (deck_id,)
        ).fetchone()[0]

        return {"basics": results, "total_added": total_added,
                "deck_card_count": card_count}

    def bling_upgrade(self, deck_id: int, dry_run: bool = False) -> dict:
        """Upgrade deck cards to blingiest printings owned.

        Returns list of swaps (applied unless dry_run=True).
        """
        deck_cards = self.conn.execute("""
            SELECT col.id as collection_id, col.printing_id, col.finish,
                   c.oracle_id, c.name,
                   p.frame_effects, p.promo_types, p.border_color,
                   p.full_art, p.promo, p.set_code, p.collector_number
            FROM collection col
            JOIN printings p ON col.printing_id = p.printing_id
            JOIN cards c ON p.oracle_id = c.oracle_id
            WHERE col.deck_id = ?
        """, (deck_id,)).fetchall()

        if not deck_cards:
            return {"swaps": [], "applied": False}

        deck = self.repo.get(deck_id)
        sub_plans = json.loads(deck["sub_plans"]) if deck and deck.get("sub_plans") else []
        hypothetical = deck and deck.get("hypothetical")

        def _bling_score(row):
            frame_effects = json.loads(row["frame_effects"]) if row["frame_effects"] else []
            promo_types = json.loads(row["promo_types"]) if row["promo_types"] else []
            score = 0
            if row["border_color"] == "borderless":
                score += 100
            if row["full_art"]:
                score += 80
            if "showcase" in frame_effects:
                score += 60
            if "extendedart" in frame_effects:
                score += 40
            if "serialized" in promo_types:
                score += 200
            if "doublerainbow" in promo_types:
                score += 150
            if row["finish"] == "foil":
                score += 20
            if row["promo"]:
                score += 10
            return score

        def _bling_tags(row):
            tags = []
            frame_effects = json.loads(row["frame_effects"]) if row["frame_effects"] else []
            promo_types = json.loads(row["promo_types"]) if row["promo_types"] else []
            if row["border_color"] == "borderless":
                tags.append("Borderless")
            if row["full_art"]:
                tags.append("Full Art")
            if "showcase" in frame_effects:
                tags.append("Showcase")
            if "extendedart" in frame_effects:
                tags.append("Extended Art")
            if "serialized" in promo_types:
                tags.append("Serialized")
            if "doublerainbow" in promo_types:
                tags.append("Double Rainbow")
            if row["finish"] == "foil":
                tags.append("Foil")
            if row["promo"]:
                tags.append("Promo")
            return tags

        swaps = []
        claimed_ids = {card["collection_id"] for card in deck_cards}

        for card in deck_cards:
            current_score = _bling_score(card)
            oracle_id = card["oracle_id"]

            if hypothetical:
                candidates = self.conn.execute("""
                    SELECT col.id as collection_id, col.printing_id, col.finish,
                           p.frame_effects, p.promo_types, p.border_color,
                           p.full_art, p.promo, p.set_code, p.collector_number
                    FROM collection col
                    JOIN printings p ON col.printing_id = p.printing_id
                    WHERE p.oracle_id = ? AND col.status = 'owned'
                      AND col.id != ?
                      AND col.id NOT IN (
                          SELECT id FROM collection WHERE deck_id = ?
                      )
                """, (oracle_id, card["collection_id"], deck_id)).fetchall()
            else:
                candidates = self.conn.execute("""
                    SELECT col.id as collection_id, col.printing_id, col.finish,
                           p.frame_effects, p.promo_types, p.border_color,
                           p.full_art, p.promo, p.set_code, p.collector_number
                    FROM collection col
                    JOIN printings p ON col.printing_id = p.printing_id
                    WHERE p.oracle_id = ? AND col.status = 'owned'
                      AND col.id != ?
                      AND col.deck_id IS NULL AND col.binder_id IS NULL
                """, (oracle_id, card["collection_id"])).fetchall()

            candidates = [c for c in candidates if c["collection_id"] not in claimed_ids]
            if not candidates:
                continue

            best = max(candidates, key=lambda r: (_bling_score(r), r["collection_id"]))
            best_score = _bling_score(best)

            if best_score > current_score:
                claimed_ids.add(best["collection_id"])
                claimed_ids.discard(card["collection_id"])
                swaps.append({
                    "name": card["name"],
                    "old_id": card["collection_id"],
                    "new_id": best["collection_id"],
                    "old_set": f"{card['set_code']}/{card['collector_number']}",
                    "new_set": f"{best['set_code']}/{best['collector_number']}",
                    "old_score": current_score,
                    "new_score": best_score,
                    "old_finish": card["finish"],
                    "new_finish": best["finish"],
                    "bling_tags": _bling_tags(best),
                })

        if not swaps or dry_run:
            return {"swaps": swaps, "applied": False}

        # Apply swaps
        for s in swaps:
            self.conn.execute(
                "UPDATE collection SET deck_id = NULL, deck_zone = NULL WHERE id = ?",
                (s["old_id"],))
            self.conn.execute(
                "UPDATE collection SET deck_id = ?, deck_zone = 'mainboard' WHERE id = ?",
                (deck_id, s["new_id"]))
            for sp in sub_plans:
                cards = sp.get("cards", [])
                if s["old_id"] in cards:
                    cards[cards.index(s["old_id"])] = s["new_id"]

        if sub_plans:
            self.conn.execute(
                "UPDATE decks SET sub_plans = ? WHERE id = ?",
                (json.dumps(sub_plans), deck_id))

        self.conn.commit()
        return {"swaps": swaps, "applied": True}

    def mana_analysis(self, deck_id: int) -> dict:
        """Analyze mana requirements for a commander deck.

        Returns pip counts, color weights, mana curve, and land recommendations.
        """
        deck = self.repo.get(deck_id)
        if not deck:
            raise ValueError(f"Deck not found: {deck_id}")

        # Commander color identity
        cmd_ci = []
        cmd_cmc = 0
        if deck["commander_oracle_id"]:
            row = self.conn.execute(
                "SELECT color_identity, cmc FROM cards WHERE oracle_id = ?",
                (deck["commander_oracle_id"],),
            ).fetchone()
            if row:
                cmd_ci = json.loads(row["color_identity"]) if isinstance(row["color_identity"], str) else row["color_identity"]
                cmd_cmc = int(row["cmc"] or 0)

        cards = self.conn.execute(
            """SELECT c.name, c.mana_cost, c.cmc, c.type_line
               FROM collection col
               JOIN printings p ON col.printing_id = p.printing_id
               JOIN cards c ON p.oracle_id = c.oracle_id
               WHERE col.deck_id = ?
               ORDER BY c.cmc, c.name""",
            (deck_id,),
        ).fetchall()

        color_symbols = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        pip_counts = {c: 0 for c in color_symbols}
        generic_total = 0
        spell_count = 0
        land_count = 0
        curve = {}

        for card in cards:
            type_line = (card["type_line"] or "").lower()
            is_land = "land" in type_line and "creature" not in type_line

            if is_land:
                land_count += 1
                continue

            spell_count += 1
            mana_cost = card["mana_cost"] or ""
            cmc = int(card["cmc"] or 0)
            bucket = min(cmc, 7)
            curve[bucket] = curve.get(bucket, 0) + 1

            symbols = re.findall(r"\{([^}]+)\}", mana_cost)
            for sym in symbols:
                if sym in color_symbols:
                    pip_counts[sym] += 1
                elif "/" in sym:
                    for part in sym.split("/"):
                        if part in color_symbols:
                            pip_counts[part] += 1
                elif sym == "X":
                    pass
                elif sym.isdigit():
                    generic_total += int(sym)

        total_colored_pips = sum(pip_counts.values())
        active_colors = {c: n for c, n in pip_counts.items() if n > 0}

        # Typical curve for comparison
        typical_curve = {0: 2, 1: 8, 2: 16, 3: 15, 4: 10, 5: 6, 6: 3, 7: 2}
        typical_total = sum(typical_curve.values())

        scaled_typical = {}
        for cmc_val in range(8):
            scaled_typical[cmc_val] = round(
                typical_curve.get(cmc_val, 0) * spell_count / typical_total
            ) if spell_count else 0

        avg_cmc = sum(cmc * count for cmc, count in curve.items()) / spell_count if spell_count else 0

        # Warnings
        warnings = []
        if avg_cmc > 3.5:
            warnings.append("HIGH avg CMC (>3.5) — deck may be too slow")
        elif avg_cmc < 2.0:
            warnings.append("VERY LOW avg CMC (<2.0) — may run out of gas")
        low_drops = curve.get(1, 0) + curve.get(2, 0)
        if spell_count and low_drops < spell_count * 0.3:
            warnings.append(f"Few 1-2 drops ({low_drops}/{spell_count})")
        high_drops = sum(curve.get(c, 0) for c in range(6, 8))
        if spell_count and high_drops > spell_count * 0.15:
            warnings.append(f"Heavy top end ({high_drops} cards at CMC 6+)")

        # Land recommendations
        recommended_lands = 38
        basics_split = {}
        if active_colors:
            nonbasic_estimate = min(land_count, recommended_lands // 3)
            basics_budget = recommended_lands - nonbasic_estimate
            basic_name_map = {"W": "Plains", "U": "Island", "B": "Swamp",
                              "R": "Mountain", "G": "Forest"}
            for color, count in sorted(active_colors.items(), key=lambda x: -x[1]):
                weight = count / total_colored_pips if total_colored_pips else 0
                basics_split[basic_name_map[color]] = {
                    "count": round(basics_budget * weight),
                    "weight": weight,
                }

        return {
            "deck_name": deck.get("name"),
            "commander_cmc": cmd_cmc,
            "commander_colors": cmd_ci,
            "spell_count": spell_count,
            "land_count": land_count,
            "pip_counts": {c: {"count": n, "name": color_symbols[c],
                               "pct": n / total_colored_pips if total_colored_pips else 0}
                           for c, n in pip_counts.items() if n > 0 or c in cmd_ci},
            "total_colored_pips": total_colored_pips,
            "generic_total": generic_total,
            "avg_cmc": avg_cmc,
            "curve": curve,
            "typical_curve": scaled_typical,
            "warnings": warnings,
            "recommended_lands": recommended_lands,
            "lands_to_add": max(0, recommended_lands - land_count),
            "basics_split": basics_split,
        }
