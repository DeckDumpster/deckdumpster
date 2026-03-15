---
name: jumpstart
description: Build a custom Jumpstart 2025-style 20-card pack from owned cards.
user-invocable: true
disable-model-invocation: true
---

# Jumpstart Pack Builder

Build custom Jumpstart 2025-style 20-card packs using cards the user actually owns. The process: choose a color + theme + rare category, find an identity card, generate a soft shape, then fill slots theme-first.

## The J25 Pack Formula (Reference)

Every J25 pack follows this formula (derived from analyzing all 121 real J25 decks):

- **20 cards total**: 8-9 lands + 11-12 non-land spells
- **Lands**: 1 Thriving land (color-matched) + 6-7 basics + 0-1 special non-basic
- **Mono-colored** (all colored spells share one color; colorless artifacts OK)
- **Rarity**: 1-2 rare/mythic, 3-5 uncommon, rest common (among non-lands)
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

5. **Price as quality proxy**: Higher-priced cards are generally more played and powerful. Use as a tiebreaker.

## Tools

All tools are invoked via `uv run python .claude/skills/jumpstart/scripts/<tool>.py <args>`.

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

### jumpstart-card-oracle.py `"<card name>"`
Read a card's full oracle text.

### jumpstart-scryfall-url.py `"Card 1" "Card 2" ... [--open]`
Generate a Scryfall search URL showing all cards (using owned printings). Add `--open` to launch in browser.

### jumpstart-insert-deck.py `--color C --theme "Theme" --description "..." "Card1" "Card2" ...`
Insert a finished pack as a hypothetical deck.

## Building a Pack (Step by Step)

### Step 1: User picks color + theme + rare category

The user says something like "Green Elves with a lord" or "Black Zombies with a bomb." If they just say "Green deck," suggest themes based on their collection and ask for a rare category.

### Step 2: Find the identity card

Search for rare/mythic candidates matching the color, theme, and category:

```bash
# Bomb (MV 4+):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r rare --mv-min 4 -o --theme elf

# Lord/Enabler (MV 1-3):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r rare --mv-max 3 -o --theme elf

# Engine (any MV):
uv run python .claude/skills/jumpstart/scripts/jumpstart-find-card.py -c G -r rare -o --theme elf
```

If no rare matches, try mythic, then broaden the theme search. Read oracle text of the top 2-3 candidates. Pick the one that most strongly defines what the pack wants to do.

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
- **Rarity budget**: 1-2 R/M, 3-5 U, rest C (among non-lands)
- **Total spells**: 11-12 (matching land count of 8-9)
- **Creature count**: 5-9 (need board presence)
- **Curve**: MV2 and MV3 each have at least 1 card
- **No MV0 spells**
- **Singletons**: every non-basic non-land card appears once

These are soft (deviate if it gets a better card):
- Exact count at each MV (+/-1 is fine)
- Creature vs non-creature at a specific MV
- Exact uncommon/common split (total rarity budget matters more)

**Curve discipline matters.** With only 8 lands in a 40-card shuffled deck (~16 lands total), top-heavy curves brick. Resist the urge to jam multiple splashy high-MV cards even when they're on-theme. Stick to the curve targets — if the shape says 1 card at MV5+, don't put 3 there.

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
