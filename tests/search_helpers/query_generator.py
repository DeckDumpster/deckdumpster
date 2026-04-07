"""Reverse parser that generates syntactically valid Scryfall-style search queries.

Inverts the grammar productions from mtg_collector/search/grammar.py to produce
random but parseable queries for generative/fuzz testing.
"""

from __future__ import annotations

import random

from mtg_collector.search.compiler import _HAS_FLAG_MAP, _IS_FLAG_MAP
from mtg_collector.search.keywords import COLOR_MAP, KEYWORD_ALIASES, RARITY_ALIASES

# ---------------------------------------------------------------------------
# Reverse alias lookup: canonical keyword -> list of aliases
# ---------------------------------------------------------------------------

_CANONICAL_TO_ALIASES: dict[str, list[str]] = {}
for _alias, _canonical in KEYWORD_ALIASES.items():
    _CANONICAL_TO_ALIASES.setdefault(_canonical, []).append(_alias)

# ---------------------------------------------------------------------------
# Canonical keywords to exclude in supported_only mode
# ---------------------------------------------------------------------------

_UNSUPPORTED = {"block", "date", "order", "direction", "unique"}

# ---------------------------------------------------------------------------
# Operator sets per keyword type
# ---------------------------------------------------------------------------

_NUMERIC_OPS = [":", "=", "!=", "<", ">", "<=", ">="]
_TEXT_OPS = [":"]
_ENUM_OPS = [":", "="]
_COLOR_OPS = [":", "=", "!=", "<", ">", "<=", ">="]

_KEYWORD_OPS: dict[str, list[str]] = {
    "color": _COLOR_OPS,
    "color_identity": _COLOR_OPS,
    "type": _TEXT_OPS,
    "oracle": _TEXT_OPS,
    "fulloracle": _TEXT_OPS,
    "mana": _TEXT_OPS,
    "mana_value": _NUMERIC_OPS,
    "power": _NUMERIC_OPS,
    "toughness": _NUMERIC_OPS,
    "powtou": _NUMERIC_OPS,
    "loyalty": _NUMERIC_OPS,
    "rarity": _COLOR_OPS,  # supports ordinal comparison
    "set": _ENUM_OPS + ["!="],
    "set_type": _ENUM_OPS,
    "artist": _TEXT_OPS,
    "flavor": _TEXT_OPS,
    "watermark": _ENUM_OPS,
    "keyword": _TEXT_OPS,
    "format": _TEXT_OPS,
    "banned": _TEXT_OPS,
    "restricted": _TEXT_OPS,
    "is_flag": _TEXT_OPS,
    "not_flag": _TEXT_OPS,
    "has_flag": _TEXT_OPS,
    "collector_number": _NUMERIC_OPS,
    "year": _NUMERIC_OPS,
    "layout": _ENUM_OPS,
    "produces": _TEXT_OPS,
}

# ---------------------------------------------------------------------------
# Value pools
# ---------------------------------------------------------------------------

_VALUE_POOLS: dict[str, list[str]] = {
    "color": list(COLOR_MAP.keys()),
    "color_identity": list(COLOR_MAP.keys()),
    "type": [
        "creature", "instant", "sorcery", "land", "enchantment", "artifact",
        "planeswalker", "legendary", "goblin", "elf", "merfolk", "dragon",
        "human", "wizard", "angel", "demon", "elemental",
    ],
    "oracle": [
        "draw", "damage", "destroy", "counter", "enters", "flying",
        "trample", "exile", "sacrifice", "graveyard", "token",
    ],
    "fulloracle": ["draw", "damage", "destroy", "enters"],
    "mana_value": [str(i) for i in range(16)],
    "power": [str(i) for i in range(16)] + ["*"],
    "toughness": [str(i) for i in range(16)] + ["*"],
    "loyalty": [str(i) for i in range(8)],
    "powtou": [str(i) for i in range(16)],
    "rarity": list(RARITY_ALIASES.keys()),
    "set": [
        "fdn", "dsk", "blb", "otj", "mh3", "spg", "woe", "lci", "mkm",
        "ecl", "fin", "tsp", "ddh", "tmp", "8ed", "roe",
    ],
    "set_type": ["expansion", "core", "masters", "draft_innovation", "commander",
                 "eternal", "alchemy", "masterpiece", "duel_deck", "starter",
                 "box", "promo", "arsenal", "from_the_vault", "spellbook"],
    "artist": ["rush", "tedin", "nielsen", "guay", "post", "avon"],
    "flavor": ["fire", "shadow", "death", "light", "dragon"],
    "watermark": ["set", "planeswalker"],
    "keyword": [
        "flying", "trample", "deathtouch", "lifelink", "haste",
        "vigilance", "first strike", "reach", "menace", "flash",
    ],
    "mana": ["{R}", "{G}", "{U}", "{B}", "{W}", "{1}", "{2}", "{3}"],
    "format": [
        "standard", "modern", "legacy", "vintage", "commander",
        "pioneer", "pauper",
    ],
    "banned": ["modern", "legacy", "standard", "commander"],
    "restricted": ["vintage"],
    "is_flag": list(_IS_FLAG_MAP.keys()),
    "not_flag": list(_IS_FLAG_MAP.keys()),
    "has_flag": list(_HAS_FLAG_MAP.keys()),
    "collector_number": [str(i) for i in range(1, 400)],
    "year": ["2020", "2021", "2022", "2023", "2024", "2025"],
    "layout": ["normal", "split", "flip", "transform", "modal_dfc", "adventure",
               "meld", "leveler", "class", "case", "saga", "mutate", "prototype",
               "battle", "augment", "host", "reversible_card", "prepare"],
    "produces": ["w", "u", "b", "r", "g"],
}

_BARE_WORDS = [
    "bolt", "lightning", "fire", "dragon", "sword", "angel",
    "goblin", "forest", "island", "elf", "serra", "jace",
]

_EXACT_NAMES = [
    "Lightning Bolt", "Sol Ring", "Counterspell", "Dark Ritual",
    "Llanowar Elves", "Swords to Plowshares", "Birds of Paradise",
]


class QueryGenerator:
    """Generates syntactically valid Scryfall-style search queries.

    Inverts the grammar productions so every generated string is guaranteed
    to parse successfully with ``parse_query``.
    """

    def __init__(
        self,
        rng: random.Random,
        *,
        supported_only: bool = True,
        max_depth: int = 3,
        max_and_terms: int = 4,
        max_or_branches: int = 3,
    ):
        self.rng = rng
        self.supported_only = supported_only
        self.max_depth = max_depth
        self.max_and_terms = max_and_terms
        self.max_or_branches = max_or_branches
        self._depth = 0

        # Build the set of canonical keywords we can use.
        # Only include keywords that actually appear in KEYWORD_ALIASES
        # (the parser rejects unknown keywords).
        _known_canonicals = set(KEYWORD_ALIASES.values())
        self._keywords = sorted(
            k for k in _KEYWORD_OPS
            if k in _known_canonicals
            and not (supported_only and k in _UNSUPPORTED)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """Return a random, syntactically valid query string."""
        self._depth = 0
        return self._gen_query()

    # ------------------------------------------------------------------
    # Grammar productions
    # ------------------------------------------------------------------

    def _gen_query(self) -> str:
        return self._gen_or_expr()

    def _gen_or_expr(self) -> str:
        count = self.rng.choices(
            range(1, self.max_or_branches + 1),
            weights=[70, 25, 5][: self.max_or_branches],
            k=1,
        )[0]
        branches = [self._gen_and_expr() for _ in range(count)]
        return " or ".join(branches)

    def _gen_and_expr(self) -> str:
        count = self.rng.choices(
            range(1, self.max_and_terms + 1),
            weights=[30, 40, 20, 10][: self.max_and_terms],
            k=1,
        )[0]
        terms = [self._gen_atom() for _ in range(count)]
        return " ".join(terms)

    def _gen_atom(self) -> str:
        roll = self.rng.random()
        if roll < 0.75:
            return self._gen_criterion()
        if roll < 0.90:
            # Negation: negate a criterion (not another atom) to avoid
            # double-negation which is syntactically fine but odd.
            return "-" + self._gen_criterion()
        # Group
        if self._depth < self.max_depth:
            self._depth += 1
            inner = self._gen_query()
            self._depth -= 1
            return "(" + inner + ")"
        # Depth exceeded — fall back to criterion
        return self._gen_criterion()

    def _gen_criterion(self) -> str:
        roll = self.rng.random()
        if roll < 0.70:
            return self._gen_keyword_expr()
        if roll < 0.90:
            return self._gen_bare_word()
        return self._gen_exact_name()

    # ------------------------------------------------------------------
    # Leaf generators
    # ------------------------------------------------------------------

    def _gen_keyword_expr(self) -> str:
        canonical = self.rng.choice(self._keywords)

        # Pick an alias that maps to this canonical keyword
        aliases = _CANONICAL_TO_ALIASES.get(canonical, [canonical])
        alias = self.rng.choice(aliases)

        # Pick a valid operator
        ops = _KEYWORD_OPS.get(canonical, [":"])
        op = self.rng.choice(ops)

        # Pick a value from the pool
        pool = _VALUE_POOLS.get(canonical, ["1"])
        value = self.rng.choice(pool)

        # Edge case: power/toughness '*' only valid with : or =
        if canonical in ("power", "toughness") and value == "*":
            if op not in (":", "="):
                op = self.rng.choice([":", "="])

        # Quote values that contain spaces
        if " " in value:
            formatted_value = f'"{value}"'
        else:
            formatted_value = value

        return f"{alias}{op}{formatted_value}"

    def _gen_bare_word(self) -> str:
        return self.rng.choice(_BARE_WORDS)

    def _gen_exact_name(self) -> str:
        name = self.rng.choice(_EXACT_NAMES)
        return f'!"{name}"'
