---
name: jumpstart
description: Build a custom Jumpstart 2025-style 20-card pack from owned cards.
user-invocable: true
disable-model-invocation: false
---

# Jumpstart Pack Builder

Build custom Jumpstart 2025-style 20-card packs using cards the user actually owns. The process: choose a color + theme + rare category, find an identity card, generate a soft shape, then fill slots theme-first.

## The J25 Pack Formula (Reference)

Every J25 pack follows this formula (derived from analyzing all 121 real J25 decks):

- **20 cards total**: 8 lands + 12 non-land spells
- **Lands**: 1 Thriving land (color-matched) + 7 basics (always)
- **Mono-colored** (all colored spells share one color; colorless artifacts OK)
- **Rarity**: 1 mythic + 1 rare (prefer mythic as identity card; fall back to 2 rares if no mythic available), 3-5 uncommon, rest common. **Rarity is determined by oracle_id, not by the specific printing owned** — if any printing of a card exists at a given rarity, the card counts as that rarity for budget purposes. **Always use the lowest rarity printing** — a card that exists at both rare and uncommon counts as uncommon. This frees up rare/mythic slots for cards that are only available at higher rarities. (e.g., Serra Angel is rare in Alpha but uncommon in Dominaria — it counts as uncommon.)
- **Creatures**: 5-8 creature-typed cards (usually 7-8)
- **Non-creature spells**: 3-7 (usually 4)
- **Curve**: MV 0 always empty. MV 2 and MV 3 always have at least 1 card each. MV 2+3 combined is 4-10 (usually 6-7). MV 5+ combined is 0-4.
- **Singletons**: all non-basic non-land cards appear once

## Rare Categories

The identity card defines the pack's game plan. Choose one:

- **Bomb** (MV 4+): A finisher the deck ramps into. Big creature with evasion, powerful enchantment, game-ending effect. The rest of the deck supports surviving and casting this. Search with `--mv-min 4`.
- **Engine** (any MV): Generates repeated value through "whenever" triggers, activated abilities, or recursive effects. The deck feeds the engine. Search without MV constraints, evaluate oracle text for repeated effects.
- **Lord/Enabler** (MV 1-3): Makes the rest of the deck better. Tribal lords, anthems, cost reducers, build-around synergy pieces. The deck goes wide to maximize the buff. Search with `--mv-max 3`.

## Card Quality Evaluation

When choosing between candidates for a slot, evaluate card quality using these signals (in priority order):

1. **Theme fit**: How well does the card advance the pack's theme? A mediocre card that's on-theme beats a powerful card that's off-theme. **Use multiple theme keywords** when searching — a single keyword misses related concepts.

2. **Synergy with identity card**: Does this card work well with the identity card specifically? If the identity is an elf lord, more elves are better. If it's a lifegain engine, cards that gain life or trigger on lifegain are better.

3. **Multiple effects**: Cards that do 2+ things are better than single-effect cards. The `jumpstart-find-card.py` tool shows effect counts automatically — prefer cards showing 2+ effects.

4. **Standalone power**: In a 20-card deck shuffled with another random 20-card deck, cards need to be independently good. Avoid narrow combo pieces.

5. **Set variety**: Prefer cards from a variety of sets over concentrating on one set. Part of the fun is seeing cards from different eras and worlds together. Some overlap is fine — don't sacrifice card quality for variety — but when candidates are close, pick the one from an underrepresented set.

6. **Price as quality proxy**: Higher-priced cards are generally more played and powerful. Use as a tiebreaker.

## Tools

All tools are invoked via `uv run python .claude/skills/jumpstart/scripts/<tool>.py <args>`.

**Host configuration:** Scripts read the server URL from `.claude/skills/jumpstart/host` (one URL per line). Override with `--host <url>` flag or `MTGC_HOST` env var. Priority: `--host` flag > `MTGC_HOST` env > `host` file > default (`https://localhost:8081`).

**IMPORTANT — one command per tool call.** Do NOT chain multiple script invocations with `&&`, `;`, or subshells. Each script call should be a separate Bash tool invocation. Chaining causes permission prompts for every sub-command.

### jumpstart-generate-shape.py `[COLOR] [--rare-category bomb|engine|lord] [--seed N]`
Generate a soft pack shape: curve distribution, creature/spell count, rarity budget. Color is W/U/B/R/G; random if omitted. Use `--seed` for reproducibility.

### jumpstart-find-card.py `[options]`
Find cards matching filters. **Always use `-o` to filter to owned cards.**

Shows quality signals: price, effect count, and effect types.

```bash
# Find identity card (bomb — MV 4+):
jumpstart-find-card.py -c G -r rare --mv-min 4 -o --theme elf

# Find identity card (lord — MV 1-3):
jumpstart-find-card.py -c G -r rare --mv-max 3 -o --theme elf

# Fill a curve slot:
jumpstart-find-card.py -m 3 -c G -r common -o --theme elf

# Broader search (drop rarity or type):
jumpstart-find-card.py -m 2 -c G -o --theme elf

# Flags:
#   -m / --cmc       Exact mana value
#   --mv-min         Minimum mana value (inclusive)
#   --mv-max         Maximum mana value (inclusive)
#   -c / --color     Color: W/U/B/R/G
#   -r / --rarity    common / uncommon / rare / mythic
#   -t / --type      Creature / Instant / Sorcery / Enchantment / Artifact
#   -o / --owned     IMPORTANT: only show cards the user owns
#   --theme          Keyword to match in oracle text, type line, or name
#   --limit N        Max results (default 50)
```

### jumpstart-search.py `"<sql_where_clause>" [--color W]`
Search owned cards using raw SQL WHERE clauses. More expressive than `jumpstart-find-card.py` — use when structured filters aren't enough. Optional `--color` restricts to mono-colored cards. Use `--schema` to see available columns.

```bash
# Find cheap removal:
jumpstart-search.py "c.oracle_text LIKE '%destroy target%' AND c.cmc <= 3"

# Find green creatures with ETB effects:
jumpstart-search.py "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%enters%'" --color G

# See available columns:
jumpstart-search.py --schema
```

### jumpstart-card-oracle.py `"<card name>"`
Read a card's full oracle text.

### jumpstart-scryfall-url.py `"Card 1" "Card 2" ... [--open]`
Generate a Scryfall search URL showing all cards (using owned printings). Add `--open` to launch in browser.

### jumpstart-insert-deck.py `--color C --theme "Theme" --description "..." "Card1" "Card2" ...`
Insert a finished pack as a hypothetical deck.

### jumpstart-odds.py `<group_size> [group_size ...] [--need N ...] [--by N] [--label L ...]`
Calculate probability of drawing specific card combinations in a Jumpstart game. Pure math — no server needed. Uses simulation (200k trials).

```bash
# Combo check: need Dark Ritual + Gwenom + a land in opening hand
jumpstart-odds.py 1 1 16 --by 8 --label "Dark Ritual" "Gwenom" "lands"

# Density check: need 5 goblins in first 20 cards from pool of 9
jumpstart-odds.py 9 --need 5 --by 20 --label "goblins"

# Flags:
#   --need N [N ...]   How many from each group (default: 1 each)
#   --by N             Cards drawn (default: 8 = opening hand + first draw)
#   --deck N           Deck size (default: 40)
#   --label L [L ...]  Optional names for each group
```

## Building a Pack (Step by Step)

### Step 1: User picks color + theme + rare category

The user says something like "Green Elves with a lord" or "Black Zombies with a bomb." If they just say "Green deck," suggest themes based on their collection and ask for a rare category.

### Step 2: Find the identity card (mythic slot)

Search for a **mythic** first — this is the preferred identity card rarity:

```bash
# Bomb (MV 4+):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r mythic --mv-min 4 -o --theme elf

# Lord/Enabler (MV 1-3):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r mythic --mv-max 3 -o --theme elf

# Engine (any MV):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r mythic -o --theme elf
```

If no mythic matches the theme, fall back to rare for the identity card (and use 2 rares total instead). Read oracle text of the top 2-3 candidates. Pick the one that most strongly defines what the pack wants to do.

### Step 2b: Find the second rare/mythic

After picking the identity card, fill the other R/M slot:
- If identity is mythic → search for a **rare** that supports the theme
- If identity is rare (mythic fallback) → search for another **rare**

This card should complement the identity card's game plan, not compete with it.

### Step 3: Generate the soft shape

```bash
uv run python .claude/skills/jumpstart/scripts/jumpstart-generate-shape.py G --rare-category lord
```

This gives: curve targets, creature count, rarity budget. The identity card consumes one R/M slot and one curve slot at its MV.

### Step 4: Fill remaining slots, ONE AT A TIME

Track these running totals as you go:
- Remaining creatures needed
- Remaining non-creature spells needed
- Remaining rarity budget (R/M, U, C)
- Remaining curve slots per MV

Maintain a **picked cards list** — before selecting any card, check that it's not already in the list. Every non-basic non-land card must be unique.

For each slot:

1. Decide what you need most: a creature or non-creature? Which MV has the most remaining slots? What rarity?
2. Search with appropriate filters + theme:
   ```bash
   uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -m 3 -c G -r common -o --theme elf
   ```
3. If zero results with `--theme`, drop it and scan manually for on-theme cards.
4. If zero results at that MV, try adjacent MVs (shifting one card by +/-1 MV is fine).
5. **Evaluate candidates** using the card quality criteria. Prefer on-theme, multi-effect, standalone good.
6. For promising candidates, read the oracle text to confirm.
7. Pick the card. Update your running totals. Move to the next slot.

**DO NOT** try to fill multiple slots at once. One card at a time. There are only 11-12 spell slots.

### Step 5: Review and present

After all slots are filled, present the complete deck list with:
- Each card's name, mana cost, type, and a brief note on why it was chosen
- The identity card highlighted
- Overall theme coherence assessment
- Mana curve summary

**Synergy reality check:** If you've identified cards that are good together, evaluate whether they actually come together often enough to matter. Use `jumpstart-odds.py` to check: (1) combo probability — how often do you have all the pieces? and (2) tribal/threshold density — how often do you hit the critical mass? A combo that happens in <15% of games is a nice bonus, not a build-around. If a card was included primarily for its synergy with one other specific card, and the odds of having both are low, consider whether a card that's independently stronger would be better.

Generate a Scryfall URL so the user can visually verify:
```bash
uv run python .claude/skills/jumpstart/scripts/jumpstart-scryfall-url.py "Card 1" "Card 2" ... --open
```

### Step 6: Insert the deck

After user approval:
```bash
uv run python .claude/skills/jumpstart/scripts/jumpstart-insert-deck.py \
    --color G --theme "Elves" \
    --description "Elf tribal with Elvish Archdruid as lord. Mana elves ramp into ..." \
    "Card 1" "Card 2" ...
```

## Soft Shape Constraints

The soft shape is a guide. These constraints are hard:
- **Rarity budget**: 1 mythic + 1 rare (fall back to 2 rares if no mythic available), 3-5 U, rest C. Rarity is by oracle_id (any printing's rarity counts)
- **Total spells**: 12 (always)
- **Lands**: 8 (always: 1 Thriving + 7 basics)
- **Creature count**: 5-9 (need board presence)
- **Curve**: MV2 and MV3 each have at least 1 card
- **No MV0 spells**
- **Singletons**: every non-basic non-land card appears once

These are soft (deviate if it gets a better card):
- Exact count at each MV (+/-1 is fine)
- Creature vs non-creature at a specific MV
- Exact uncommon/common split (total rarity budget matters more)

**Curve discipline matters.** With only 8 lands in a 40-card shuffled deck (~16 lands total), top-heavy curves brick. Resist the urge to jam multiple splashy high-MV cards even when they're on-theme. Stick to the curve targets — if the shape says 1 card at MV5+, don't put 3 there.

## Card Selection Rules

These rules apply to ALL card choices in the pack:

1. **No wrath effects.** Do not include board wipes, mass removal, "destroy all creatures", or similar mass disruption. These packs are meant to be fun and interactive — wraths are miserable in Jumpstart.

2. **No triple-pip mana costs.** Avoid cards with 3+ colored pips of the same color in their mana cost (e.g., {W}{W}{W}, {B}{B}{B}{B}). With only 8 lands per half-deck (~16 lands total in a shuffled game), triple-pip costs are unreliable. Double-pip is the maximum.

3. **Focus on interactivity.** Prefer cards that create interesting game states over cards that shut opponents out. Prioritize creatures with combat tricks, ETB effects, auras, equipment, and targeted removal over pillowfort, stax, or prison effects. The goal is two players trading blows, not one player locked out.

## Theme Search Strategy

The `--theme` flag does a simple substring match. For broad themes, **run multiple searches with related keywords**:

- Angels: "angel", "flying", "life", "lifelink", "vigilance"
- Zombies: "zombie", "graveyard", "dies", "sacrifice"
- Goblins: "goblin", "haste", "sacrifice", "damage"
- Elves: "elf", "mana", "forest", "druid"
- Lifegain: "life", "lifelink", "gain", "soul"
- Tokens: "token", "create", "populate"
- Ramp: "mana", "land", "search your library", "add"

If the first search returns 0 results, **always** drop `--theme` and search the full pool — many on-theme cards won't match a simple keyword.

## Notes

- All cards must come from the user's collection (use `-o` flag)
- If the user's collection is thin for a theme, suggest alternative themes
- Packs are inserted as hypothetical decks (visible in web UI, no physical card assignment)
