"""Constants for deck builder service."""

DECK_SIZE = 100
DEFAULT_FORMAT = "commander"

# Recommended land counts by color count
LAND_COUNTS = {1: 36, 2: 37}  # 3+ colors default to 38

# Infrastructure: tag groups every Commander deck needs.
# A card matching ANY tag in a group counts toward that group's minimum.
INFRASTRUCTURE = {
    "Ramp": {
        "tags": {
            "ramp", "mana-dork", "mana-rock", "adds-multiple-mana",
            "extra-land", "repeatable-treasures",
        },
        "min": 10,
    },
    "Card Advantage": {
        "tags": {
            "draw", "card-advantage", "tutor", "repeatable-draw",
            "burst-draw", "impulse", "repeatable-impulsive-draw",
            "wheel", "curiosity-like", "life-for-cards", "bottle-draw",
        },
        "min": 12,
    },
    "Targeted Disruption": {
        "tags": {
            "removal", "creature-removal", "artifact-removal",
            "enchantment-removal", "planeswalker-removal",
            "removal-exile", "removal-toughness", "disenchant",
            "counter", "edict", "bounce", "graveyard-hate",
            "land-removal", "hand-disruption", "burn-creature",
            "lockdown", "humble", "control-changing-effects",
        },
        "min": 14,
    },
    "Mass Disruption": {
        "tags": {
            "boardwipe", "sweeper-one-sided", "multi-removal",
            "mass-land-denial", "tax",
        },
        "min": 6,
    },
}

# Flat set of all infrastructure tags (for excluding from plan suggestions)
INFRASTRUCTURE_TAGS = set()
for _group in INFRASTRUCTURE.values():
    INFRASTRUCTURE_TAGS.update(_group["tags"])

PLAN_TARGET = 30
LAND_TARGET_DEFAULT = 38

# Mana curve hard limits by type group (CMC bracket -> (min, max))
# Used for audit warnings only.
CREATURE_CURVE_LIMITS = {
    0: (0, 0),
    1: (0, 4),
    2: (4, 10),
    3: (4, 10),
    4: (3, 8),
    5: (2, 6),
    6: (1, 4),
    7: (0, 3),  # 7+
}

NONCREATURE_CURVE_LIMITS = {
    0: (0, 3),
    1: (4, 10),
    2: (5, 12),
    3: (4, 10),
    4: (2, 6),
    5: (0, 4),
    6: (0, 2),
    7: (0, 1),  # 7+
}

# Mana curve targets by type group (CMC bracket -> target count)
# Midpoints of the hard limits above — used for curve-fit scoring.
CREATURE_CURVE_TARGETS = {
    0: 0, 1: 2, 2: 7, 3: 7, 4: 5, 5: 4, 6: 2, 7: 1,
}

NONCREATURE_CURVE_TARGETS = {
    0: 1, 1: 7, 2: 8, 3: 7, 4: 4, 5: 2, 6: 1, 7: 0,
}

AVG_CMC_TARGET = (2.8, 3.5)


# Basic land name -> color letter
BASIC_LANDS = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}

SNOW_BASICS = {
    "Snow-Covered Plains": "W",
    "Snow-Covered Island": "U",
    "Snow-Covered Swamp": "B",
    "Snow-Covered Mountain": "R",
    "Snow-Covered Forest": "G",
}

# Cards that bypass the singleton rule
ANY_NUMBER_CARDS = {
    "Persistent Petitioners",
    "Rat Colony",
    "Relentless Rats",
    "Shadowborn Apostle",
    "Dragon's Approach",
    "Slime Against Humanity",
}

# Bling scoring weights
BLING_WEIGHTS = {
    "finish_foil": 2,
    "finish_etched": 3,
    "frame_extended": 2,
    "frame_showcase": 3,
    "frame_borderless": 4,
    "full_art": 2,
    "promo": 1,
}

# Zone constants
ZONE_MAINBOARD = "mainboard"
ZONE_SIDEBOARD = "sideboard"
ZONE_COMMANDER = "commander"

# Embedding tag inference threshold (cosine similarity)
DESCRIPTION_MATCH_THRESHOLD = 0.80

# Autofill composite scoring weights — raw integer values.
# Static weights are constant throughout the fill. Dynamic weights
# (deficit, curve_fit) ramp from START to MAX as the deck fills,
# using an exponential curve (fill_ratio^8) so they're negligible
# until ~75% full, then dominate near 100%.
# User-adjustable weights are stored per-deck in plan JSON.
AUTOFILL_WEIGHTS = {
    "edhrec": 3,            # Per-commander EDHREC inclusion (cards popular with THIS general)
    "salt": 2,              # Salt / annoyance (lower = better)
    "price": 1,             # Log-scaled monetary value (proxy for power level)
    "plan_overlap": 3,      # Cards matching multiple plan categories score higher
    "novelty": 3,           # Inverse global EDHREC rank (less popular overall = more interesting)
    "recency": 2,           # Newer set release = fresher card
    "bling": 4,             # Full-art/borderless/extended/showcase
    "random": 0,            # Uniform jitter for variety
}

# Rarity: starts high (splashy mythics/rares early), ramps down linearly.
# Flat at start_weight until start_at, then linear to end_weight at end_at,
# flat at end_weight after that.
DYNAMIC_WEIGHT_RARITY = {
    "start_weight": 8,
    "end_weight": 2,
    "start_at": 0.20,       # begin declining at 20% fill
    "end_at": 0.80,         # reach minimum at 80% fill
}

# Dynamic weight ranges: ramp from start to max as deck fills
DYNAMIC_WEIGHT_DEFICIT = (1, 100)    # (start, max) — role deficit
DYNAMIC_WEIGHT_CURVE_FIT = (1, 20)   # (start, max) — mana curve fit
DYNAMIC_WEIGHT_EXPONENT = 20         # fill_ratio^N — matches static weights at ~85%, dominant at ~95%

# Land suggestion scoring weights
LAND_WEIGHTS = {
    "color_coverage": 0.35,  # Covers needed colors, weighted by pip demand
    "untapped": 0.20,        # Enters untapped bonus
    "edhrec": 0.20,          # Lower rank = better
    "bling": 0.15,           # Foil/borderless/extended
    "random": 0.10,          # Variety jitter
}


PLAN_GENERATE_PROMPT = """You are an expert Magic: The Gathering Commander/EDH deck builder.

I need you to create 2 different deck plan variants for a Commander deck led by:

**Commander:** {commander_name}
**Type:** {commander_type}
**Mana Cost:** {commander_mana_cost}
**Color Identity:** {colors_str}
**Oracle Text:** {commander_oracle_text}

## Available Tags
These are the real tag names from our card database. You MUST use only these exact tag names in your plan targets.
{tag_list}

## Type Tags
In addition to the functional tags above, every card has `type:X` tags derived from its card types and creature subtypes (e.g. `type:creature`, `type:pirate`, `type:artifact`, `type:dragon`). You do NOT need to list these — just use the format `type:X` with the lowercase type/subtype name when relevant.

**Type synergy commanders:** Read the commander's oracle text carefully. If it references a creature type (e.g. "whenever a Pirate enters", "Goblins you control get +1/+1"), a card type (e.g. "whenever you cast an Artifact spell", "enchantments you control have..."), or shares a type that has tribal payoffs, include a `type:X` target for that type. Type targets should be LARGE — typically 25-40 cards — because the deck's entire strategy revolves around having enough cards of that type. This is intentionally much higher than functional tag targets like removal (10) or ramp (8). Not every variant needs a type target, but at least one variant for a type-caring commander should go deep on the tribal/type angle.

## Custom Query Targets
When the commander's strategy involves card properties that tags don't cover (e.g. specific power/toughness, oracle text patterns, keyword abilities), you can create **custom query targets** using SQL WHERE clauses.

Use the `query_db` tool to test your queries against the real database before including them. Verify the query is valid and returns a reasonable number of cards.

Custom query target format in the JSON response:
"role-key": {{"count": N, "query": "SQL WHERE clause", "label": "Human Label"}}

Example: For Duskana, the Rage Mother (synergy with 2/2 creatures):
"equal-pt-creatures": {{"count": 12, "query": "json_extract(p.raw_json, '$.power') = '2' AND json_extract(p.raw_json, '$.toughness') = '2' AND card.type_line LIKE '%Creature%'", "label": "2/2 Creatures"}}

The WHERE clause will be injected into a query like:
SELECT ... FROM cards card JOIN printings p ON p.oracle_id = card.oracle_id WHERE (<your clause>) AND ...

**Important:** Only use custom queries when tags don't cover the need. Most roles should still use tags.

## DB Schema (for query_db tool)
{db_schema}

## Infrastructure (every Commander deck needs these)
{infra_lines}

## Base Template
A 99-card Commander deck has 99 cards plus the commander:
- ~38 Lands (use the tag "lands" for this target)
- ~10 Ramp (use the broad category "Ramp" — searches all ramp sub-tags)
- ~12 Card Advantage (use "Card Advantage" — searches draw, tutor, impulse, etc.)
- ~14 Targeted Disruption (use "Targeted Disruption" — searches removal, counter, bounce, etc.)
- ~6 Mass Disruption (use "Mass Disruption" — searches boardwipe, sweeper, tax, etc.)
- ~19 remaining slots for the deck's strategy/theme

## Commander Adjustments
- If commander provides card draw → fewer Card Advantage slots
- If commander IS removal → fewer Targeted Disruption slots
- If commander is cheap (1-3 MV) → can shave a land or two
- If commander is expensive (6+ MV) → more ramp, possibly 39 lands

## Your Task
1. First, analyze the commander's abilities. If the commander has synergies that tags don't cover, use the `query_db` tool to test WHERE clauses that capture those synergies. Be efficient — typically 2-5 queries.
2. Then create exactly 2 plan variants, each with a different strategic angle.

**CRITICAL: Every key in "targets" must be an exact tag name from the Available Tags list above, a `type:X` tag (lowercase type/subtype name), the special value "lands", one of the broad infrastructure categories ("Ramp", "Card Advantage", "Targeted Disruption", "Mass Disruption"), or a custom query target (dict with count/query/label).** Do not invent functional tag names — but `type:X` tags are always valid as long as X is a real Magic card type or creature subtype.

For each variant, provide:
1. A short name (2-3 words)
2. A 1-2 sentence strategy description
3. A targets dict mapping tag names to card counts (or custom query dicts)

**Every variant MUST include these fixed infrastructure targets:**
- "lands" (~38)
- "Ramp" (~10)
- "Card Advantage" (~12)
- "Targeted Disruption" (~14)
- "Mass Disruption" (~6)

You may adjust the infrastructure counts based on what the commander provides (e.g. fewer Card Advantage if commander draws cards), but every variant must include all 5 infrastructure categories. You only need to differentiate the ~19 strategy-specific slots between variants.

**Strategy targets: keep it tight.** Generate only 2-3 strategy-specific targets per variant. One broad theme tag (e.g. "counters-matter", "synergy-token") plus 1-2 supporting tags or a type target. Do NOT over-subdivide the strategy into many small categories. Fewer, broader targets produce better decks.

Cards can have multiple tags, so a single card can satisfy multiple targets. Because of this overlap, the sum of all targets will typically be HIGHER than 99 (e.g. 110-130). That's expected and correct — it means some cards serve double duty.

After analysis, respond with ONLY valid JSON in this exact format:
{{
  "variants": [
    {{
      "name": "Variant Name",
      "strategy": "Brief strategy description.",
      "targets": {{
        "lands": 38,
        "Ramp": 10,
        "Card Advantage": 12,
        "Targeted Disruption": 14,
        "Mass Disruption": 6,
        "example-strategy-tag": 15,
        "custom-role": {{"count": 12, "query": "WHERE clause here", "label": "Custom Role"}}
      }}
    }}
  ]
}}"""

DB_SCHEMA_FOR_PLAN = (
    "cards(oracle_id PK, name, type_line, mana_cost, cmc, oracle_text, colors JSON, color_identity JSON)\n"
    "printings(printing_id PK, oracle_id FK, set_code, collector_number, rarity, artist, raw_json)\n"
    "collection(id PK, printing_id FK, finish, status, deck_id FK, binder_id FK, deck_zone)\n"
    "card_tags(oracle_id, tag) — embedding-inferred functional tags\n"
    "salt_scores(card_name PK, salt_score)\n"
    "\n"
    "Key joins: cards -> printings via oracle_id, printings -> collection via printing_id, "
    "cards -> card_tags via oracle_id\n"
    "Useful raw_json fields: json_extract(p.raw_json, '$.edhrec_rank'), "
    "json_extract(p.raw_json, '$.power'), json_extract(p.raw_json, '$.toughness'), "
    "json_extract(p.raw_json, '$.keywords')\n"
    "Colors/color_identity are JSON arrays as TEXT (e.g. '[\"B\",\"G\"]') — use LIKE for filtering."
)

QUERY_DB_TOOL = {
    "name": "query_db",
    "description": (
        "Run a read-only SQL query against the card database. "
        "Returns up to 20 rows. Use to test WHERE clauses, "
        "check tag availability, verify card counts for the "
        "commander's color identity."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "SELECT query to execute",
            }
        },
        "required": ["sql"],
    },
}

PLAN_GENERATE_MODEL = "claude-sonnet-4-5-20250929"
PLAN_GENERATE_MAX_TOKENS = 4000
PLAN_GENERATE_MAX_TOOL_ROUNDS = 10
