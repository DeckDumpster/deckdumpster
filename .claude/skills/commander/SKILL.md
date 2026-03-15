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

The template totals **108 slots across 6 categories** — intentionally over 99 because many cards serve multiple roles. A Sol Ring is both Ramp and a Plan Card. A Swords to Plowshares is Targeted Disruption but could also be a Plan Card in a lifegain deck.

| Category | Target | Description |
|----------|--------|-------------|
| Lands | 38 | Mana base (including utility lands) |
| Ramp | 10 | Mana acceleration — mana dorks, mana rocks, land tutors |
| Card Advantage | 12 | Card draw, selection, recursion, impulse draw |
| Targeted Disruption | 12 | Single-target removal, counters, targeted exile |
| Mass Disruption | 6 | Board wipes, mass bounce, mass exile |
| Plan Cards | 30 | Cards advancing the deck's strategy/win condition |

Every card you add is **explicitly assigned** to one or more categories via `--categories`. The audit tool tracks counts based on these assignments, not regex. Use your MTG knowledge to decide what role a card fills. MORE OVERLAP is BETTER. Get the total to 130 or more if you can.

## Search Hints by Category

Run `commander-sample-queries.py --<category>` to get sample SQL WHERE clauses for any category. Covers all template roles (ramp, card-advantage, targeted-disruption, mass-disruption, lands) and common sub-plan themes (sacrifice, reanimation, tokens, counters, discard, etb, voltron, tribal). Run `--list` to see all available categories.

Use the sample queries as starting points, then adapt with additional filters (CMC caps, type constraints, rarity, etc.) as needed.

## Tools

All tools are invoked via `uv run python .claude/skills/commander/scripts/<tool>.py <args>`.

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
Print sample SQL WHERE clauses for a card category. Covers template roles (ramp, card-advantage, targeted-disruption, mass-disruption, lands) and common sub-plan themes (sacrifice, reanimation, tokens, counters, discard, etb, voltron, tribal). Use the output as starting points for `commander-search.py`.

### commander-mana-analysis.py `<deck_id>`
Mana base sizing tool. Run after all spells are added, before adding lands. Shows colored pip counts, color weight percentages, mana curve, and recommends total land count and basic land split based on pip ratios, average CMC, and ramp count.

### commander-deck-audit.py `<deck_id>`
Full audit: template role distribution, sub-plan progress, mana curve, EDHREC recommendations (if data exists), next priority. All counts are based on explicit `--categories` assignments from `commander-add-card.py`.

### commander-search.py `<deck_id> "<sql_where_clause>"` | `--schema`
Search owned cards using a SQL WHERE clause. The query runs against `cards c`, `printings p`, and `collection col` (already joined). Cards already in the deck are excluded, and color identity is filtered to match the commander. EDHREC inclusion rates are shown when data exists.

Run `--schema` to see all available columns. Examples:
```
commander-search.py 62 "c.oracle_text LIKE '%destroy target%' AND c.cmc <= 3"
commander-search.py 62 "c.type_line LIKE '%Creature%' AND c.oracle_text LIKE '%enters%' AND c.cmc <= 3"
commander-search.py 62 "p.rarity IN ('rare', 'mythic') AND c.cmc <= 4"
```

### commander-add-card.py `<deck_id> <collection_id> --categories "<name>" ...`
Add a card to the deck. Validates singleton rule and color identity. Use `--categories` to assign the card to template roles and/or sub-plan categories. A card can belong to multiple categories. Examples:
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

## Three-Phase Process

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
5. Present the sub-plan categories to the user for approval
6. Save everything with `commander-save-plan.py <deck_id> "<plan>" --sub-plans '<json>'`

Sub-plan targets should sum to roughly the Plan Cards target (30) but can overlap — a card can satisfy multiple sub-plans. The audit tool tracks progress against each sub-plan.

### Phase 3: Add Cards — Spells First, Lands Last

Build the deck's spells before the mana base. You cannot know the right land count or color distribution until you know what spells you are casting (EDHREC, Chimera Gaming, and other guides all recommend this). The order below ensures every support card directly reinforces the gameplan.

#### Build order (non-land categories first)

1. **Plan Cards (win conditions & synergy)** — Start here. These define what the deck does. Use the sub-plan categories to guide your search — fill the sub-plans in priority order. Everything else exists to support these. Choose BIG SPLASHY cards. Rare, mythic rare, expensive, lots of bling.
2. **Ramp** — Mana acceleration that enables the plan. Choose ramp that fits the curve (e.g., 2-mana rocks/dorks for a 4+ CMC commander). Prefer cards that fetch multiple land, artifacts that generate multple mana.
3. **Card Advantage** — Draw, selection, and recursion to keep the engine running. Prefer card advantage that synergizes with the plan.
4. **Targeted Disruption** — Single-target removal, counters, and interaction. Pick answers that handle the threats your deck cares about.
5. **Mass Disruption** — Board wipes and mass removal. Choose wipes that leave your board intact when possible (asymmetric wipes).
6. **Lands (last)** — After all spells are chosen, build the mana base. Use the deck's color pip requirements and mana curve to determine the right split of basics, duals, utility lands, and color-fixing.

#### Iterative loop (within each category)

For each category in the order above:

1. **Audit** — Run `commander-deck-audit.py <deck_id>` to see current distribution and sub-plan progress
2. **Search** — Use `commander-search.py` to find candidates for the current category. Run **multiple searches** with different queries to get a diverse candidate pool. See "Search Hints by Category" above.
3. **Compare** — For every slot, find **at least 2-3 candidate cards** and choose the best one. Never add the first card you find. What matters shifts as the deck fills up:

   **Early (0-50 cards) — prioritize impact:**
   - Splashy, powerful cards first. Rare/mythic over common/uncommon.
   - Cards that define the deck's identity and advance the plan
   - Multi-effect cards (does two things) over single-effect
   - Special treatments: prefer Borderless, Extended Art, Showcase, Full Art printings
   - EDHREC popularity — higher inclusion rate = more proven

   **Late (50+ cards) — prioritize curve and gaps:**
   - Check the mana curve in the audit. Fill CMC gaps — if you're heavy at 3, look for 1-2 drops.
   - Flexible cards (good early AND late) beat narrow ones
   - Prefer cards that fill multiple categories (a removal spell that also draws, a ramp creature with an ETB)
   - If a sub-plan is short, weight candidates toward filling it
4. **Add** — After comparing candidates, add the winner with explicit category assignments:
   `commander-add-card.py <deck_id> <collection_id> --categories "<role>" "<sub-plan>" ...`
   Always specify ALL categories the card belongs to (template roles + sub-plans).
5. **Repeat** until the category is filled, then move to the next category

**DO NOT add the first card you find.** Always search, compare at least 2-3 options, explain why the chosen card beats the alternatives, then add it. This produces better decks than grabbing the first match.

**DO NOT add multiple cards at once.** Evaluate deck slots at a time, it's easier to build coherent decks that way. DO NOT combine commands with newlines, that makes the user need to approve the commands.

#### Sizing the mana base (Phase 3, step 6)

Once all spells are in, run `commander-mana-analysis.py <deck_id>` to get pip counts, color weights, curve data, and a recommended land count with basic split. Then:

- Use the recommended land count as a starting point (accounts for curve and ramp)
- Add nonbasic lands first: dual lands, utility lands that support the plan (e.g., sacrifice lands for a sacrifice deck)
- Fill remaining slots with basics, weighted by the pip percentages from the analysis
- Re-run the analysis after adding lands to verify the final count

### Completion

When `commander-deck-audit.py` shows 99/99 cards, the deck is complete. Run `commander-bling-it-up.py <deck_id>` to upgrade all cards to the blingiest printings owned. Summarize the final build for the user.

## Notes

- Hypothetical decks allow cards already assigned to other decks/binders
