---
name: jumpstart
description: Build a custom Jumpstart 2025-style 20-card pack from owned cards.
user-invocable: true
disable-model-invocation: false
---

# Jumpstart Pack Builder

Build custom Jumpstart 2025-style 20-card packs using cards the user actually owns.

## The J25 Pack Formula (Reference)

Every J25 pack follows this formula (derived from analyzing all 121 real J25 decks):

- **20 cards total**: 8 lands + 12 non-land spells
- **Lands**: 1 Thriving land (color-matched) + 7 basics (always)
- **Mono-colored** (all colored spells share one color; colorless artifacts OK). **Hybrid mana cards are fine** — a W/G hybrid card can go in either a white or green mono-color pack since it can be cast with either color. **Multicolor packs** are also supported — the identity card is multicolored, but most cards in the deck will be mono-colored in one of the two colors. A WU deck is mostly white cards and blue cards, with a few WU gold cards — it doesn't need to be packed with multicolor cards.
- **Rarity**: 2-3 rare/mythic slots, decided per-deck based on what's available. Valid combos: (M+R), (R+R), (M+R+R), (R+R+R). Choose based on what the theme needs — splashier decks can run 3 R/M. Remainder: 3-5 uncommon, rest common. **Rarity is determined by oracle_id, not by the specific printing owned** — if any printing of a card exists at a given rarity, the card counts as that rarity for budget purposes. **Always use the lowest rarity printing** — a card that exists at both rare and uncommon counts as uncommon. This frees up rare/mythic slots for cards that are only available at higher rarities. (e.g., Serra Angel is rare in Alpha but uncommon in Dominaria — it counts as uncommon.)
- **Creatures**: 5-8 creature-typed cards (usually 7-8)
- **Non-creature spells**: 3-7 (usually 4)
- **Curve**: MV 0 always empty. MV 2 and MV 3 always have at least 1 card each. MV 2+3 combined is 4-10 (usually 6-7). MV 5+ combined is 0-4.
- **Singletons**: all non-basic non-land cards appear once

## How Themes Work

J25 analysis shows themes exist on a spectrum from tight engine to loose flavor. **All three tiers produce good decks.** The theme guides card selection, not deck mechanics — it tells you *which* good cards to pick.

### Engine themes
Almost every card participates in the mechanic. The deck doesn't function without it. Examples: graveyard (11/12 on-theme), draw-two (11/12), mill (12/12), landfall (7-10/11), flash (8-10/12). Build these by finding **2-4 explicit payoffs** and filling the rest with enablers that naturally do the thing.

### Tribal themes
The creature type IS the synergy. Elves naturally make mana and go wide. Vampires naturally drain and have lifelink. Clerics naturally gain life and sacrifice. You don't need "Elves you control get +1/+1" for an elf deck to feel like an elf deck — 8 elves doing elf things is plenty. **0-3 tribal payoff cards is normal.** Even the most synergistic tribal decks (goblins: 6-7 payoffs) still run 2-3 off-tribe utility cards.

### Flavor themes
The name is a vibe, the cards are individually good. Real J25 examples: "Encounter" has 1 fight card in 12 — it's actually "+1/+1 counters on green creatures." "Explorers" often has 0 explore cards — it's "green value creatures that find lands." These decks differentiate through card selection coherence, not mechanical density. **Don't force payoffs that aren't there.** If the theme is "big green creatures," just pick the best big green creatures.

### Synergy guidance
- **Don't stress about payoff density. Stress about card selection coherence.** A "Lifegain" deck with 8 creatures that incidentally have lifelink and 3 Ajani's Pridemate-style payoffs is great. A "Lifegain" deck packed with 8 explicit "whenever you gain life" payoffs and not enough life gain sources is terrible.
- **Every creature should do something.** Only 0.5% of J25 creatures are vanilla (no text). 95% have meaningful abilities beyond keywords. If choosing between a vanilla 3/3 and a 2/2 with an ETB, take the 2/2.
- **2-4 off-theme utility cards is normal** — removal, card draw, pump spells. Never force 12/12 on-theme.
- **Removal is optional.** Many real J25 decks run zero removal (elves, landfall, tokens). Aggro decks that just play creatures and attack don't need it. Include removal when it's on-theme (Dragon's Fire in dragons) or the deck needs time.
- **Match card advantage to game plan speed.** Aggro (zealots, warriors): 0-2 draw effects. Midrange/control (wizards, bookworms): 7-11. Don't force draw into a deck that wants to curve out and attack.

## Building a Pack

Packs can start from either direction:

### Top-down: theme first
The user names a theme (tribal, mechanical, or flavor). Search for cards that fit, build an oversized pool, cut to 12.

### Bottom-up: card or mechanic first
The user names a specific card, sees a cool rare, or notices a cluster of cards that work together. Build outward from that seed — find what supports it, what fills the gaps, what gives it a name.

### The process (either direction)

**1. Establish the seed.** Either a theme name or 1-3 cards to build around. If the user is vague ("green deck"), search broadly to find what clusters exist in their collection.

**2. Search broadly.** Cast a wide net with multiple searches. The goal is 15-25+ candidates — much more than the final 12. Use `jumpstart-search.py` with different oracle text patterns, type lines, subtypes, and rarity filters. A single search always misses related cards.

**3. Read oracle text on promising candidates.** Confirm cards actually do what you think. Use `jumpstart-card-oracle.py` for quick lookups.

**4. Identify the synergy tier.** Based on what you found, is this an engine (most cards must participate), tribal (creature type coherence), or flavor (individually good cards with a shared vibe)? This determines how aggressively to prioritize on-theme cards during cuts.

**5. Insert the oversized pool.** Use `jumpstart-insert-deck.py`. The user will trim in the UI, or you can help cut.

**6. Cut to 12.** Prioritize:
   - Standalone card quality — cards need to be independently good in a shuffled 40-card game
   - Theme coherence — cards should look like they belong together, but don't over-force synergy
   - Rarity budget — 2-3 R/M, 3-5 U, rest C
   - Curve — MV 2+3 combined 4-10, MV 5+ max 4
   - Creature count — 5-9 (usually 7-8)

**7. Generate a Scryfall URL** so the user can visually verify the final list.

## Tools

All tools are invoked via `uv run python .claude/skills/jumpstart/scripts/<tool>.py <args>`.

**Host configuration:** Scripts read the server URL from `.claude/skills/jumpstart/host` (one URL per line). Override with `--host <url>` flag or `MTGC_HOST` env var. Priority: `--host` flag > `MTGC_HOST` env > `host` file > default (`https://localhost:8081`).

**IMPORTANT — one command per tool call.** Do NOT chain multiple script invocations with `&&`, `;`, or subshells. Each script call should be a separate Bash tool invocation. Chaining causes permission prompts for every sub-command.

### jumpstart-search.py `"<sql_where_clause>"`
Search owned cards using raw SQL WHERE clauses. The core exploration tool — use it to find candidates, scout what's available in a color, check creature type density, find rares, etc. Use `--schema` to see available columns. All color/hybrid filtering is done via the WHERE clause directly.

```bash
# Mono-green creatures
jumpstart-search.py "c.type_line LIKE '%Elf%' AND c.colors = '[\"G\"]'"

# Cards castable with only green mana (mono-green + G hybrids + colorless)
jumpstart-search.py "c.mana_cost NOT LIKE '%{W}%' AND c.mana_cost NOT LIKE '%{U}%' AND c.mana_cost NOT LIKE '%{B}%' AND c.mana_cost NOT LIKE '%{R}%' AND c.cmc <= 3"

# Rarity search
jumpstart-search.py "p.rarity IN ('rare', 'mythic') AND c.cmc <= 5 AND c.colors = '[\"G\"]'"

# See available columns
jumpstart-search.py --schema
```

### jumpstart-card-oracle.py `"<card name>"`
Read a card's full oracle text. Use to confirm a card does what you think before including it.

### jumpstart-generate-shape.py `[COLOR] [--rare-category bomb|engine|lord] [--rm-count 2|3] [--seed N]`
Generate a soft pack shape: curve distribution, creature/spell count, rarity budget. Color is W/U/B/R/G; random if omitted. `--rm-count` forces 2 or 3 rare/mythic slots (random if omitted). Use `--seed` for reproducibility.

### jumpstart-insert-deck.py `--color C --theme "Theme" --description "..." "Card1" "Card2" ...`
Insert a finished pack as a idea deck. Color can be a single letter (W/U/B/R/G/C) or a pair (WU/BR/etc). Multicolor decks get one thriving land (first color) and split basics between colors.

### jumpstart-remove-cards.py `--deck <id> "Card1" "Card2" ...`
Remove cards by name from a idea deck. Useful for trimming oversized pools down to the final 12 spells.

### jumpstart-scryfall-url.py `"Card 1" "Card 2" ... [--open]`
Generate a Scryfall search URL showing all cards (using owned printings). Add `--open` to launch in browser.

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

## Final Deck Constraints

Hard constraints:
- **Rarity budget**: 2-3 rare/mythic slots — valid combos: (M+R), (R+R), (M+R+R), (R+R+R). Choose based on theme needs. 3-5 U, rest C. Rarity is by oracle_id (any printing's rarity counts)
- **Total spells**: 12 (always)
- **Lands**: 8 (always: 1 Thriving + 7 basics)
- **Creature count**: 5-9 (need board presence)
- **Curve**: MV2 and MV3 each have at least 1 card
- **No MV0 spells**
- **Singletons**: every non-basic non-land card appears once

Soft (deviate if it gets a better card):
- Exact count at each MV (+/-1 is fine)
- Creature vs non-creature at a specific MV
- Exact uncommon/common split (total rarity budget matters more)

**Curve discipline matters.** With only 8 lands in a 40-card shuffled deck (~16 lands total), top-heavy curves brick. Resist the urge to jam multiple splashy high-MV cards even when they're on-theme. Stick to the curve targets — if the shape says 1 card at MV5+, don't put 3 there.

## Card Selection Rules

These rules apply to ALL card choices in the pack:

1. **No wrath effects.** Do not include board wipes, mass removal, "destroy all creatures", or similar mass disruption. These packs are meant to be fun and interactive — wraths are miserable in Jumpstart.

2. **Triple-pip mana costs are OK but rare.** Cards with 3 colored pips (e.g., {1}{W}{W}{W}) are allowed — ~6% of real J25 decks include one. Don't load up on them (1 per deck max), and avoid 4+ pips. Double-pip is the sweet spot.

3. **Focus on interactivity.** Prefer cards that create interesting game states over cards that shut opponents out. Prioritize creatures with combat tricks, ETB effects, auras, equipment, and targeted removal over pillowfort, stax, or prison effects. The goal is two players trading blows, not one player locked out.

## Notes

- All cards must come from the user's collection (searches return only owned cards)
- If the user's collection is thin for a theme, suggest alternative themes or pivot to bottom-up from a strong card
- Packs are inserted as idea-state decks (visible in web UI, no physical card assignment)
