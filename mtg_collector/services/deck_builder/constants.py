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
            "extra-land", "cost-reducer", "repeatable-treasures",
        },
        "min": 10,
    },
    "Card Advantage": {
        "tags": {
            "draw", "card-advantage", "tutor", "repeatable-draw",
            "burst-draw", "impulse", "repeatable-impulsive-draw",
            "wheel", "curiosity-like", "life-for-cards", "bottle-draw",
        },
        "min": 10,
    },
    "Targeted Disruption": {
        "tags": {
            "removal", "creature-removal", "artifact-removal",
            "enchantment-removal", "planeswalker-removal",
            "removal-exile", "removal-toughness", "disenchant",
            "counter", "edict", "bounce", "graveyard-hate",
            "land-removal", "hand-disruption", "burn-creature",
        },
        "min": 10,
    },
    "Mass Disruption": {
        "tags": {
            "boardwipe", "sweeper-one-sided", "multi-removal",
            "mass-land-denial",
        },
        "min": 3,
    },
}

# Flat set of all infrastructure tags (for excluding from plan suggestions)
INFRASTRUCTURE_TAGS = set()
for _group in INFRASTRUCTURE.values():
    INFRASTRUCTURE_TAGS.update(_group["tags"])

PLAN_TARGET = 30
LAND_TARGET_DEFAULT = 37

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
# User-adjustable weights are stored per-deck in plan JSON.
AUTOFILL_WEIGHTS_RAW = {
    "edhrec": 3,            # Per-commander EDHREC inclusion (cards popular with THIS general)
    "salt": 2,              # Salt / annoyance (lower = better)
    "price": 1,             # Log-scaled monetary value (proxy for power level)
    "plan_overlap": 3,      # Cards matching multiple plan categories score higher
    "novelty": 3,           # Inverse global EDHREC rank (less popular overall = more interesting)
    "recency": 2,           # Newer set release = fresher card
    "bling": 4,             # Full-art/borderless/extended/showcase
    "rarity": 3,            # Higher rarity (mythic > rare > uncommon > common) preferred
    "random": 0,            # Uniform jitter for variety
    "curve_fit": 2,         # Cards in under-represented CMC buckets score higher
}

# Normalize to sum to 1.0 for scoring
def _normalize_weights(raw: dict) -> dict:
    total = sum(raw.values())
    if total == 0:
        return {k: 0.0 for k in raw}
    return {k: v / total for k, v in raw.items()}

AUTOFILL_WEIGHTS = _normalize_weights(AUTOFILL_WEIGHTS_RAW)

# Land suggestion scoring weights
LAND_WEIGHTS = {
    "color_coverage": 0.35,  # Covers needed colors, weighted by pip demand
    "untapped": 0.20,        # Enters untapped bonus
    "edhrec": 0.20,          # Lower rank = better
    "bling": 0.15,           # Foil/borderless/extended
    "random": 0.10,          # Variety jitter
}


PRIME_PROMPT = """# Commander Deck Builder

## Your tools
- `mtg deckbuilder query "SELECT ..."` — read anything from the DB
- `mtg deckbuilder add <id> "Card Name"` — add a card
- `mtg deckbuilder remove <id> "Card Name"` — remove a card
- `mtg deckbuilder swap <id> "Out" "In"` — swap cards
- `mtg deckbuilder fill-lands <id>` — auto-fill basic lands
- `mtg deckbuilder audit <id>` — see category balance, curve, plan progress
- `mtg deckbuilder check <id>` — validate legality
- `mtg deckbuilder create "Commander Name"` — create a deck
- `mtg deckbuilder show <id>` — view the deck list
- `mtg deckbuilder plan <id> --set tag1=N,tag2=N` — set plan targets (must be real tag names from card_tags)
- `mtg deckbuilder plan <id>` — show plan progress
- `mtg deckbuilder plan <id> --clear` — clear the plan

## Resuming after context loss
If you've lost context mid-build, run `audit <id>` to see where you are.
The plan targets and all deck contents persist in the DB.

## Schema

```
cards(oracle_id PK, name, type_line, mana_cost, cmc, oracle_text, colors JSON, color_identity JSON)
printings(printing_id PK, oracle_id FK, set_code, collector_number, rarity, artist, raw_json)
collection(id PK, printing_id FK, finish, status, deck_id FK, binder_id FK, deck_zone, deck_note)
card_tags(oracle_id, tag) — embedding-inferred functional tags
salt_scores(card_name PK, salt_score)
decks(id PK, name, description, format, plan JSON)
prices(set_code, collector_number, source, price_type, price, observed_at)
```

Key joins:
- cards → printings via oracle_id
- printings → collection via printing_id
- cards → card_tags via oracle_id
- colors, color_identity, finishes, promo_types are JSON arrays stored as TEXT — use json_each() or LIKE

Useful fields in printings.raw_json:
```sql
json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank
json_extract(p.raw_json, '$.prices.usd') AS price_usd
json_extract(p.raw_json, '$.keywords') AS keywords
json_extract(p.raw_json, '$.legalities.commander') AS legality
json_extract(p.raw_json, '$.power') AS power
json_extract(p.raw_json, '$.toughness') AS toughness
```

## About tags

Tags in card_tags are inferred by embedding similarity — they are a useful
starting filter but NOT ground truth. Expect false positives (cards tagged
with roles they don't actually fill) and false negatives (cards missing tags
they deserve). Always read oracle_text to verify a card actually does what
the tag claims.

When tags don't cover what you need, query oracle_text directly:
```sql
WHERE card.oracle_text LIKE '%fights target%'
WHERE card.oracle_text LIKE '%deals damage equal to its power%'
WHERE card.oracle_text LIKE '%whenever a creature dies%'
```

Use tags to cast a wide net, then use your MTG knowledge + oracle text to
make the final call.

## Color identity filtering

color_identity is a JSON array stored as TEXT (e.g. '["B","G"]'). To filter
to a commander's identity, exclude colors NOT in the identity. For a B/G
commander, exclude W, U, and R:
```sql
AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%W%')
AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%U%')
AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%R%')
```
Colorless cards (NULL or '[]') pass all filters, which is correct.

## How to find cards

Search is a gradual filtering process:

**Step 1 — Cast a wide net.** Query by tag(s) OR oracle_text patterns,
filtered to color identity + owned + unassigned + not already in deck.
Use `IN (...)` with multiple related tags, not just one — e.g. for ramp
use `IN ('ramp', 'mana-dork', 'mana-rock')` since a card may have one
tag but not another.

**Step 2 — Read and evaluate.** Always SELECT oracle_text. Read the top
results and judge whether each card actually fills the role you want.
Tags may be wrong — a card tagged 'removal' might not actually remove
anything. Trust oracle text over tags.

**Step 3 — Rank candidates.** Use multiple signals to pick the best cards:

1. **EDHREC rank** (lower = more popular in Commander):
   `json_extract(p.raw_json, '$.edhrec_rank')`
2. **Role count** — how many DIFFERENT infrastructure/plan categories
   the card serves. Count across categories (ramp + card advantage),
   not within one category (ramp + mana-dork are the same role).
3. **Mana efficiency** — lower CMC is generally better. For creatures,
   power + toughness relative to mana cost.
4. **Dollar value** — higher-value cards tend to be more powerful:
   `CAST(json_extract(p.raw_json, '$.prices.usd') AS REAL)`
5. **Salt score** — lower is better for playgroup harmony:
   `SELECT salt_score FROM salt_scores WHERE card_name = ?`

No single signal is decisive. EDHREC rank is the best default sort, but
a 2-role card at rank 500 is often better than a 1-role card at rank 50.
Use your judgment.

## Excluding cards already in the deck

Always exclude cards already in the deck by oracle_id to avoid singleton
errors:
```sql
AND card.oracle_id NOT IN (
    SELECT p2.oracle_id FROM collection c2
    JOIN printings p2 ON c2.printing_id = p2.printing_id
    WHERE c2.deck_id = <DECK_ID>
)
```

## Example queries

Owned unassigned ramp in B/G identity, not already in deck #5:
```sql
SELECT DISTINCT card.name, card.mana_cost, card.cmc, card.oracle_text,
       json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank
FROM cards card
JOIN printings p ON p.oracle_id = card.oracle_id
JOIN card_tags ct ON ct.oracle_id = card.oracle_id
WHERE ct.tag IN ('ramp', 'mana-dork', 'mana-rock')
  AND card.type_line NOT LIKE '%Land%'
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%R%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%W%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%U%')
  AND card.oracle_id NOT IN (
      SELECT p2.oracle_id FROM collection c2
      JOIN printings p2 ON c2.printing_id = p2.printing_id
      WHERE c2.deck_id = 5
  )
  AND EXISTS (
      SELECT 1 FROM collection c
      WHERE c.printing_id = p.printing_id
        AND c.status = 'owned' AND c.deck_id IS NULL AND c.binder_id IS NULL
  )
GROUP BY card.oracle_id
ORDER BY edhrec_rank ASC NULLS LAST
LIMIT 20
```

Cards with fight/bite effects (oracle text search when no tag exists):
```sql
SELECT DISTINCT card.name, card.mana_cost, card.cmc, card.oracle_text,
       json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank
FROM cards card
JOIN printings p ON p.oracle_id = card.oracle_id
WHERE (card.oracle_text LIKE '%fights target%'
    OR card.oracle_text LIKE '%deals damage equal to its power to target%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%R%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%W%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%U%')
  AND EXISTS (
      SELECT 1 FROM collection c
      WHERE c.printing_id = p.printing_id
        AND c.status = 'owned' AND c.deck_id IS NULL AND c.binder_id IS NULL
  )
GROUP BY card.oracle_id
ORDER BY edhrec_rank ASC NULLS LAST
LIMIT 15
```

Cards in deck #5 grouped by tag:
```sql
SELECT card.name, ct.tag, card.type_line, card.cmc
FROM collection c
JOIN printings p ON c.printing_id = p.printing_id
JOIN cards card ON p.oracle_id = card.oracle_id
LEFT JOIN card_tags ct ON ct.oracle_id = card.oracle_id
WHERE c.deck_id = 5
ORDER BY ct.tag, card.cmc
```

Mana curve histogram for a deck:
```sql
SELECT CASE WHEN card.cmc >= 7 THEN '7+' ELSE CAST(CAST(card.cmc AS INT) AS TEXT) END AS cmc_bucket,
       COUNT(*) AS count
FROM collection c
JOIN printings p ON c.printing_id = p.printing_id
JOIN cards card ON p.oracle_id = card.oracle_id
WHERE c.deck_id = 5 AND card.type_line NOT LIKE '%Land%'
GROUP BY cmc_bucket ORDER BY cmc_bucket
```

Available tags and their card counts:
```sql
SELECT tag, COUNT(*) AS cnt FROM card_tags GROUP BY tag ORDER BY cnt DESC
```

Top 10 owned unassigned nonbasic lands in Rakdos identity:
```sql
SELECT DISTINCT card.name, card.oracle_text, p.set_code,
       json_extract(p.raw_json, '$.edhrec_rank') AS edhrec_rank
FROM cards card
JOIN printings p ON p.oracle_id = card.oracle_id
WHERE card.type_line LIKE '%Land%'
  AND card.type_line NOT LIKE '%Basic%'
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%W%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%U%')
  AND (card.color_identity IS NULL OR card.color_identity NOT LIKE '%G%')
  AND EXISTS (
      SELECT 1 FROM collection c
      WHERE c.printing_id = p.printing_id
        AND c.status = 'owned' AND c.deck_id IS NULL AND c.binder_id IS NULL
  )
ORDER BY edhrec_rank ASC NULLS LAST
LIMIT 10
```

## The deck template

Every deck has two layers:

**Infrastructure** (same for every deck):
| Category            | Min | Tags                                                    |
|---------------------|-----|---------------------------------------------------------|
| Lands               |  37 | (by type line)                                          |
| Ramp                |  10 | ramp, mana-dork, mana-rock, adds-multiple-mana, etc.    |
| Card Advantage      |  10 | draw, tutor, impulse, wheel, curiosity-like, etc.       |
| Targeted Disruption |  10 | removal, counter, bounce, edict, graveyard-hate, etc.   |
| Mass Disruption     |   3 | boardwipe, sweeper-one-sided                            |

**Plan** (~30 cards, deck-specific):
Tags chosen collaboratively with the user based on the commander's
strategy. ~15+ cards serve double duty across categories.

## Workflow
1. Create the deck
2. Discuss strategy with the user (win conditions, game plan)
3. Set plan — break the ~30 plan card slots into sub-roles with
   numeric targets. Targets can be tag names (from card_tags) or
   MTG keyword abilities (trample, deathtouch, haste, etc.).
   Tags are counted via card_tags; keywords are counted by
   oracle text match. Query available tags first. Get user
   approval before proceeding.
4. Fill infrastructure (ramp, card advantage, disruption)
5. Fill plan cards (deck-specific synergy/theme)
6. Fill lands
7. Audit, iterate, validate
8. Present the deck to the user for review. User may reject cards
   and ask for replacements.

## Add cards ONE AT A TIME

Do NOT batch-add cards. For each slot:
1. Query for candidates (cast a wide net)
2. Read the results — evaluate oracle text, CMC, type, synergy
3. Pick ONE card and add it
4. Move on to the next slot

This ensures you are making deliberate choices, not bulk-adding the
first N results of a query. Every card should earn its slot.

## Card selection heuristics

### Multi-role cards
Multi-role cards > single-role — a creature that also draws cards or
removes threats is worth more than a vanilla beater. Judge by reading
oracle text, not by counting tags (tags have overlapping synonyms
within the same category).

### Commander synergy
Every card should connect to the commander's game plan. Ask: "Does
this card get better because my commander is in play, or does it make
my commander better?" Generic good-stuff is fine for infrastructure,
but plan cards should specifically synergize with the commander.

### Mana curve
Target avg CMC 2.8-3.5, heavy on 1-3 CMC. As you add cards, be
aware of the curve you're building. Don't add a 5-drop when you
already have plenty at that cost — look for a 2 or 3 CMC alternative
that fills the same role. Spread your curve across card types too:
don't put all your cheap cards in one category (e.g. all cheap ramp
but expensive creatures).

### Card type diversity
A good deck has a mix of creatures, instants, sorceries, artifacts,
and enchantments. Don't over-index on one type. Creatures are the
backbone but you need instant-speed interaction and resilient
non-creature permanents too.

### Variety
Don't just pick the top N results from one query. Vary your sources:
different tags, oracle text searches, different sort criteria. A deck
that's all EDHREC-rank-1000 staples plays the same every game. Include
some cards that are uniquely good with YOUR commander even if they
have a high EDHREC rank.

### Other
- Prefer creatures that do something (ETB, dies trigger, attack trigger)
- Bling: foil/borderless when available (add handles this automatically)
- Salt: <2.0 preferred, >3.0 avoid unless essential
"""
