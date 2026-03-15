---
name: commander
description: Build a Commander deck using the Command Zone 2025 template.
user-invocable: true
disable-model-invocation: true
---

# Commander Deck Builder

Build a Magic: The Gathering Commander deck from the user's collection using the **Command Zone 2025 template** (episode 658).

## Format Rules

- **Exactly 100 cards** (99 + 1 commander)
- **Singleton**: Only one copy of each card (basic lands exempt)
- **Color Identity**: Every card must match the commander's color identity
- **Commander**: A legendary creature (or card with "can be your commander")
- All cards must come from the user's collection (local DB only, no internet)

## Command Zone 2025 Template

38 lands, 61 nonland cards, 1 Commander. Template:

Plan Cards: 34 (Cards advancing the deck's strategy/win condition)
Ramp: 10 (Mana acceleration: mana dorks, mana rocks, land tutors)
Card Advantage: 12 (Card draw, selection, recursion, impulse draw)
Targeted Disruption: 12 (Single-target removal, counters, targeted exile)
Mass Disruption: 6 (Board wipes, mass bounce, mass exile)
Mana-producing lands: 38

Multiple roles: The template totals more than 99 because many cards should serve multiple roles.

**Explicitly assign** cards to categories via `--categories`. The add-card tool tracks counts based on these assignments. Use your MTG knowledge to decide what role a card fills. MORE OVERLAP is BETTER. Get the total to 90 or more if you can.

## Ideal Mana Curve Minimums

Plan cards will be woven throughout.

CMC 0: 0 (don't bother)
CMC 1: 5 (strong utility, disruption/removal only)
CMC 2: 17 (strong utility, disruption/removal, enters effects on creatures, cantrips, ramp)
CMC 3: 17 (ramp, utility creatures, disruption, card draw)
CMC 4: 12 (utility, modal choices)
CMC 5: 7 (high-impact cards)
CMC 6+: 10 (powerful effects: game-ending threats, board wipes, repeatable card advantage)

## Tools

All tools are invoked via `uv run python .claude/skills/commander/scripts/<tool>.py <args>`.

### commander-find.py `[options]`
Browse owned legendary creatures for commander selection. Run with `--help` for all filter flags (colors, CMC, set year, type, oracle text, sort).

### commander-create-deck.py `<commander name query>`
Search collection for legendary creatures and create a deck. If multiple matches, prints all — re-run with a more specific query. Pre-populates template role categories for tracking.

### commander-save-plan.py `<deck_id> "<plan text>" [--sub-plans '<json>']`
Save the deck plan/theme and sub-plan categories. Sub-plans JSON format:
```json
[{"name": "Counter Synergy", "target": 10, "search_hint": "counter"}]
```
- `name`: display name for the sub-category
- `target`: how many cards you want in this sub-category
- `search_hint`: optional, for reference only

### commander-sample-queries.py `--<category>` | `--list`
Print sample SQL WHERE clauses for a card category. This is a **growing query library** — it covers template roles (ramp, card-advantage, targeted-disruption, mass-disruption, lands) and common sub-plan themes (sacrifice, reanimation, tokens, counters, discard, etb, voltron, tribal). Use the output as starting points for `commander-search.py`.

### commander-mana-analysis.py `<deck_id>`
Mana base sizing tool. Run after all spells are added, before adding lands. Shows colored pip counts, color weight percentages, mana curve, and recommends total land count and basic land split based on pip ratios, average CMC, and ramp count.

### commander-search.py `<deck_id> "<sql_where_clause>"` | `--schema`
Search owned cards using a SQL WHERE clause. The query runs against `cards c`, `printings p`, and `collection col` (already joined). Cards already in the deck are excluded, and color identity is filtered to match the commander. EDHREC inclusion rates are shown when data exists.

Run `--schema` to see all available columns. Examples:
```
commander-search.py 62 "c.oracle_text LIKE '%destroy target%' AND c.cmc <= 3"
commander-search.py 62 "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%enters%' AND c.cmc <= 3"
commander-search.py 62 "p.rarity IN ('rare', 'mythic') AND c.cmc <= 4"
```

### commander-add-card.py `<deck_id> <collection_id> --categories "<name>" ...`
Add a card to the deck. Validates singleton rule and color identity. After adding, **automatically prints deck status**: nonland count, mana curve progress, next category to fill, and phase-appropriate selection guidance. When all 61 nonland cards are in, it tells you to proceed to Phase 4. Use `--categories` to assign the card to template roles and/or sub-plan categories. A card can belong to multiple categories. Examples:
```
--categories "Ramp"
--categories "Targeted Disruption" "Plan Cards"
--categories "Plan Cards" "+1/+1 Counter Synergy" "Legendary Synergy"
--categories "Lands"
```
`--categories` is required — the tool will reject adds without it.

### commander-add-basics.py `<deck_id> --plains N --island N --forest N [--mountain N] [--swamp N]`
Bulk-add basic lands to the deck. Prefers full-art printings, then printings from the commander's set. Use this after the mana analysis to fill the land base quickly.

### commander-bling-it-up.py `<deck_id> [--dry-run]`
Upgrade every card in the deck to the blingiest printing you own (matched by `oracle_id`). Bling ranking: Serialized > Double Rainbow > Borderless > Full Art > Showcase > Extended Art > Foil > Promo > standard. Use `--dry-run` to preview changes without applying them. Run this as a final polish step after the deck is complete.

## Deck building process

### Phase 1: Choose Commander & Create Deck

The user provides a commander or asks for help choosing one.

1. Search with `commander-create-deck.py "<name>"`
2. If multiple matches, help the user choose, then re-run with a specific name
3. The tool creates a hypothetical commander deck with template categories pre-populated

### Phase 2: Make a Plan with Sub-Categories

Analyze the commander's abilities and propose 2-3 deck themes to the user.

1. Consider the commander's oracle text, color identity, and type
2. Present themes that magnify the commander's upsides
3. If the commander has downsides, propose strategies that turn them into advantages
4. Once a theme is agreed, define **2-4 sub-plan categories** that break the Plan Cards into specific roles. Each sub-plan has a name and a target count. Examples:
   - A reanimation deck: `{"name": "Reanimation", "target": 12}`, `{"name": "Discard Enablers", "target": 8}`
   - A counters deck: `{"name": "+1/+1 Counter Synergy", "target": 12}`, `{"name": "Counter Payoffs", "target": 8}`
   - A tokens deck: `{"name": "Token Generators", "target": 14}`, `{"name": "Anthem Effects", "target": 6}`
5. **Check the query library** — run `commander-sample-queries.py --list` to see if existing categories overlap with your sub-plans. Re-use their tested queries during card search when they align. If your sub-plan categories aren't covered, you may add them after deckbuilding.
6. Present the sub-plan categories to the user for approval
7. Save with `commander-save-plan.py <deck_id> "<plan>" --sub-plans '<json>'`

Sub-plan targets should sum to roughly the Plan Cards target (30) but can overlap — a card can satisfy multiple sub-plans. Progress is tracked automatically by `commander-add-card.py`.

### Phase 3: Add 61 nonland cards

**Start by finding a good Plan card to go with the commander.** The output of `commander-add-card.py` will tell you what's next — it prints deck status, curve progress, the next category to fill, and phase-appropriate guidance after every add. Follow its instructions.

Repeat this loop until add-card says "61 NONLAND CARDS COMPLETE":

1. **Search** — Use `commander-search.py` to find candidates for the category suggested by the last add-card output. Run **multiple searches** with different queries for a diverse pool.

2. **Compare** — Follow the selection guidance from the add-card output. Always compare at least 2-3 options and explain why the winner beats the alternatives.

3. **Add ONE card** — `commander-add-card.py <deck_id> <collection_id> --categories "<role>" "<sub-plan>" ...`
   Assign ALL categories the card belongs to (template roles + sub-plans). Read the output — it tells you what to do next. Go back to step 1.

**DO NOT add the first card you find.** Search, compare, then add.

**DO NOT FILL ENTIRE CATEGORIES.** **LISTEN TO ADD CARD.** It CHANGES as you add cards, helping you balance card additions.

#### Phase 4: Mana base

When add-card says "61 NONLAND CARDS COMPLETE", run `commander-mana-analysis.py <deck_id>` to get pip counts, color weights, curve data, and a recommended land count with basic split. Then:

- Use the recommended land count as a starting point (accounts for curve and ramp)
- Add nonbasic lands first, again use a variety of searches to find the right colors
- Fill remaining slots with basics, weighted by the pip percentages from the analysis
- Re-run the analysis after adding lands to verify the final count

### Completion

When the deck has 99 cards (+1 commander = 100), it's complete. Run `commander-bling-it-up.py <deck_id>` to upgrade all cards to the blingiest printings owned. Summarize the final build for the user.

## Notes

- Hypothetical decks allow cards already assigned to other decks/binders
- **Contributing new queries:** When you define a new sub-plan category for a commander that isn't already covered by an existing query category, consider adding it to this tool's `CATEGORIES` dict so it can be re-used in future deck builds. Add a corresponding test in `tests/test_commander_queries.py` with expected staple cards.

