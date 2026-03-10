# Master Deck Builder Plan

## Phase 1: Foundation — Tags in the DB

### 1.1: Clean up local tree — DONE

- Created `feature/phase1-tags` branch from `origin/main` (schema v32).
- Experiment work preserved on `agent-printing-ids` branch (commit `125df78`):
  WIP commit with schema v31 (deck_note, salt_scores, card_tags, plan +
  deck_label), cache salt command, deck detail UI overhaul, DeckRepository
  plan/note/label support, tag_descriptions updates, archidekt exporter.
  **These migrations will need to be renumbered** when applied to main
  (main is at v32; the WIP used v28-v31 for different features).
- `tag_all_cards.json` (4.4 MB, 151 tags, 115k pairs) is untracked and
  carried over — source of truth for tag data.
- Experiment scripts (`scripts/fetch_tag_cards*.py`, `scripts/test_*.py`,
  etc.) are untracked and preserved in the working directory.

### 1.2: Load Scryfall tags into `card_tags` — DONE

- Added `card_tags` table as schema v33 migration.
- `mtg cache tags` command fetches all tags from Scryfall API (~12 min),
  or loads from a local JSON file with `--file tag_all_cards.json`.
- `mtg cache all` automatically runs tag loading after card/printing cache
  (uses `~/.mtgc/tag_all_cards.json` if present for fast path).
- Only inserts tags for oracle_ids that exist in local `cards` table.

### 1.3: Tag search on the Collection page — DONE

- Server: added correlated subquery `(SELECT GROUP_CONCAT(ct.tag) ...)`
  to all 3 collection query variants (normal, include-unowned base/full).
  Returns `card_tags` array on each card JSON object.
- Client: added Tag multi-select filter in sidebar (same pattern as
  Set/Subtype). Tags populated from loaded data. Filters use AND logic
  (card must have ALL selected tags). Wired into clear/hasAnyFilter.

### 1.4: Ship it — DONE

Deploy via standard `deploy/deploy.sh`. Run `mtg cache tags` on the
deployed instance to populate.

---

## Phase 2: Deck Creation UI — DONE

### 2.1: Clean up decks.html — DONE

Current state: `decks.html` has list view (deck grid) and detail view (card
grid with category pills, mana curve). API endpoints exist in
`crack_pack_server.py`: GET/POST/PUT/DELETE for `/api/decks` and
`/api/decks/{id}/cards`.

**New user flow:**
1. User lands on `/decks` → sees deck list (existing).
2. "New Commander Deck" button → modal or inline form.
3. User searches their collection for a General (text input, autocomplete
   against owned legendary creatures).
4. Selecting a General calls `POST /api/decks` with the commander name.
5. Redirect to deck detail view showing the empty deck with commander.

**Server changes:**
- `POST /api/decks` already exists. May need to accept `commander_name` and
  call `DeckBuilderService.create_deck()` which validates commander legality,
  assigns the best owned copy, and creates the deck.
- Add `GET /api/collection/search?q=...&type=legendary+creature` for
  commander search (or reuse existing collection search with type filter).

**Client changes:**
- Add "New Deck" button to deck list view.
- Commander search modal with text input → fetch results → select → create.
- Wire existing detail view to show the new deck.

### 2.2: Ship it — DONE

---

## Phase 3: Deck Planning — DONE

### 3.1: "Make a Deck Plan" — DONE

From the deck detail view (with commander selected, deck mostly empty), user
clicks "Generate Plan". This calls Claude to create deck plan options.

**Template**: `architecture/COMMANDER_DECK_TEMPLATE.md` — Command Zone
99-card breakdown:
- 38 lands, 10 ramp, 12 card advantage, 12 targeted removal, 6 board wipes,
  ~25 standalone, ~10 enhancers, ~7 enablers.
- CMC curve targets and commander-based adjustments (Episode 659).

**Server side:**
- `POST /api/decks/{id}/plan` — sends commander info + template to Claude,
  asks for 2-3 plan variants (e.g. "aggressive", "controlling", "combo").
- Each plan is a JSON object with category slot counts (may deviate from
  template based on commander abilities) and a short strategy description.
- Uses `DeckBuilderService.set_plan()` to store the chosen plan.
- SSE streaming for the Claude response (same pattern as ingest processing).

**Client side:**
- "Generate Plan" button in deck detail header.
- Display plan options as cards/tabs. User picks one.
- Selected plan shows as a checklist in the sidebar: category → target count
  → current count.

**Claude prompt includes:**
- Commander name, colors, oracle text, mana cost.
- The template slot counts as a starting point.
- Commander adjustment rules (e.g. "commander provides draw → reduce card
  advantage slots").
- Ask for specific strategy/theme and how slot counts should be adjusted.

### 3.2: Ship it — DONE

---

## Phase 3.5: Fix Plan to use real tags — DONE

### Problem
Plan generation asked Claude for abstract categories (`ramp`,
`card_advantage`, `standalone`, etc.) — not real tag names from `card_tags`.
The whole point of the plan is to produce targets in terms of tags so
autofill can look them up directly. No mapping layer should be needed.

### Fix (completed)
- Changed Claude prompt to include all available tags from DB.
- Targets are now **real tag names** with numeric counts.
- Sums are >99 because cards have multiple tags (expected overlap).
- `_get_plan_progress()` simplified: counts by tag, "lands" by type line.
- UI displays tag names directly (no hardcoded category labels).
- Test fixture now seeds card_tags from `tag_all_cards.json`.
- Canned plan result saved for future test mocking.

### Verified
Tested with Stonebrow, Krosan Hero — Claude returned real tags:
`ramp`, `mana-rock`, `draw`, `boardwipe`, `evasion`, `synergy-token`,
`gives-evasion`, `anthem`, `combat-trick`, etc.

---

## Phase 4: Autofill — DONE

### 4.1: Fill deck from plan + tags — DONE

Given a plan (tag-based targets) and the user's collection, automatically
select cards to fill each tag target.

**How it works:**
1. For each tag target in the plan, query `card_tags` JOIN `collection` for
   owned cards matching that tag, filtered by commander color identity.
2. Rank candidates using a **composite score** (see below).
3. Fill up to the target count for each tag. Cards already in the deck
   are excluded. A card used in one tag target isn't reused in another.

**Composite ranking score (autofill weights):**

| Signal              | Weight | Source                                | Direction       | Notes |
|---------------------|--------|---------------------------------------|-----------------|-------|
| EDHREC popularity   | 0.15   | `raw_json $.edhrec_rank`              | lower = better  | Primary signal for card quality |
| Bling               | 0.20   | frame_effects, full_art, promo        | higher = better | Full-art, borderless, extended art, showcase |
| Random              | 0.15   | uniform random [0,1)                  | —               | Keeps suggestions fresh across runs |
| Plan tag overlap    | 0.15   | card tags ∩ plan target categories    | more = better   | Multi-role cards that fill several plan needs |
| Novelty             | 0.15   | `log2(edhrec_rank)` or per-commander  | higher = better | Less popular cards make games more interesting |
| Recency             | 0.10   | `sets.released_at`                    | newer = better  | Fresher cards feel more fun |
| Salt / annoyance    | 0.05   | `salt_scores.salt_score`              | lower = better  | Avoid grief cards |
| Monetary value      | 0.05   | `raw_json $.prices.usd` (log-scaled)  | higher = better | Proxy for power level |

Phase 5 (card replacement) will expose weight tuning to the user.

### 4.2: Haiku tag validation — DONE

Scryfall tags have significant false positives (e.g. "Demystify" tagged
`boardwipe`, "Grove of the Burnwillows" tagged `mana-rock`). Haiku
validates ALL of a card's tags on first encounter during autofill, caching
results in `card_tag_validations` (schema v35). Future queries are instant
cache hits.

- Overfetches 3x candidates to account for filtering.
- SSE streaming shows per-card validation progress in the UI.
- Backfill logic handles cards partially validated from earlier runs.
- Without API key, suggestions are shown unvalidated with a warning banner.
- Tag hints in `TAG_ROLE_HINTS` give Haiku precise definitions (e.g. ramp
  requires NET INCREASE in mana sources — fetchlands are not ramp).

**Server side:**
- `POST /api/decks/{id}/autofill` — SSE stream with progress events,
  returns proposed additions grouped by tag.
- Does NOT auto-commit. Returns suggestions for user to review.
- `POST /api/decks/{id}/cards` (existing) to actually add approved cards.

**Client side:**
- "Autofill" button in deck detail view (only enabled when a plan exists).
- Shows proposed cards per tag with checkboxes. User can accept/reject
  individual suggestions.
- "Add Selected" button commits chosen cards to the deck.

### 4.3: Deck detail UI improvements — DONE

#### Grid view with column controls
- Table/Grid toggle in deck detail view bar.
- Grid view shows card images with rarity/set gradient borders and foil overlay.
- Column controls (+/-) adjust grid from 3-8 columns per row.

#### Plan category click-to-filter
- Plan progress categories are clickable — clicking filters the card list/grid
  to only cards with that tag.
- Filter banner shows active filter with Clear button.
- Works in both table and grid views.

#### Card detail tags
- Card detail page shows validated Scryfall tags with color-coded badges
  (green=valid, red=invalid with strikethrough, grey=unvalidated).
- Tags loaded on-demand via `GET /api/card/tags?oracle_id=...`.
- Validation delegated to `DeckBuilderService.get_validated_tags()` (SOLID —
  tag validation logic lives in the service, not the HTTP handler).

#### Remove deck_note, derive roles from tags
- Removed `deck_note` field from all reads/writes. Column stays in schema
  (no migration needed) but is no longer used anywhere.
- Removed `annotate_card()` method, `--note` CLI args, notes dict from
  `_api_deck_add_cards`.
- Card roles in deck detail are now derived from `(card tags) ∩ (plan targets)`.
  Multi-valued, always accurate, never stale. Damnation correctly shows under
  both "Creature Removal" and "Board Wipes".
- `DeckRepository.get_cards()` returns `tags` via GROUP_CONCAT subquery.

### 4.4: Tag coverage audit

Audit the collection for cards that may fall through the cracks of the
current autofill scoring:

1. **Cards with zero tags** — query `cards` LEFT JOIN `card_tags` WHERE
   `card_tags.oracle_id IS NULL` AND the card is in the collection. These
   cards will never be suggested by autofill since it queries by tag.
   Check if any are legitimately useful (e.g. new cards Scryfall hasn't
   tagged yet) and need manual tag backfill.

2. **Cards that autofill never suggests** — beyond zero-tag cards, some
   tagged cards may be consistently out-scored. Run autofill across a
   few representative commanders and collect the "always ignored" set.
   Determine if the scoring weights or tag assignments need adjustment.

3. **Tag coverage gaps** — compare tags that exist in `card_tags` against
   tags that plans actually request. If plans routinely request tags that
   have very few or zero matching owned cards, surface these as "acquire"
   suggestions or flag the tag mapping as incomplete.

### 4.4: Ship it

---

## Phase 5: Card Replacement

### 5.1: Replace a card and get suggestions

User selects a card in their deck and says "replace this". System suggests
alternatives from the collection.

**How it works:**
1. Look up the card being removed — get its tags from `card_tags`.
2. Find other owned cards with overlapping tags, same color identity
   constraint, not already in this deck.
3. Rank using the same composite score as autofill, **plus** tag overlap
   (more shared tags = more similar role) and mana value proximity.
4. Present top N suggestions.
5. User can adjust ranking weights (e.g. prefer uniqueness over popularity,
   or prefer budget cards over expensive ones).

**Server side:**
- `GET /api/decks/{id}/cards/{collection_id}/replacements` — returns ranked
  list of replacement candidates with their tags and why they match.
- Accepts optional weight overrides as query params.

**Client side:**
- Right-click or button on a card in deck view → "Find Replacement".
- Sidebar or modal shows replacement candidates with weight sliders.
- Clicking one does a swap (remove old, add new) via existing API.

### 5.2: Ship it

---

## Phase 6: Intelligent Land Autofill

### 6.1: Color-fixing land selection

Current `fill_lands` just counts mana pips and distributes basics
proportionally. This works but ignores the user's owned dual lands,
fetch lands, utility lands, and color-fixing needs.

**How it works:**
1. Analyze the deck's color requirements: pip counts per color, number of
   cards with demanding costs (e.g. {W}{W}{W}, {U}{U}), curve by color.
2. Query owned lands: duals, fetches, shocks, check lands, pain lands,
   filter lands, utility lands — anything that produces colored mana.
3. Prioritize color-fixing lands that cover the deck's weakest colors or
   most demanding costs. A 4-color deck with heavy white pips needs more
   white sources than a splash color.
4. Fill remaining slots with basics proportional to pip distribution.
5. Suggest utility lands (Command Tower, Reliquary Tower, etc.) from the
   user's collection.

**Ranking signals for lands:**
- Number of colors produced (more = better for multicolor decks)
- Enters untapped vs tapped (untapped = better)
- Covers weak colors (colors with few sources relative to pip demand)
- Fetchable by other lands in the deck (e.g. shocks are fetchable)

### 6.2: Ship it

---

## Reference

### Key files
- `mtg_collector/db/schema.py` — schema v36, `card_tags` at v33,
  `salt_scores`/`plan`/`deck_note` at v34, `card_tag_validations` at v35,
  `type_line` backfill + `edhrec_commander_cards` at v36
- `mtg_collector/cli/cache_cmd.py` — `cache_all()`, add `cache_tags()`
- `mtg_collector/services/deck_builder/service.py` — `DeckBuilderService`,
  autofill with composite scoring, Haiku validation integration
- `mtg_collector/services/deck_builder/tag_validator.py` — `TagValidator`,
  Haiku-based tag validation with `TAG_ROLE_HINTS` and DB caching
- `mtg_collector/services/deck_builder/constants.py` — `INFRASTRUCTURE`
  mapping (categories → tag sets)
- `mtg_collector/static/collection.html` — collection page, client-side
  filtering
- `mtg_collector/static/decks.html` — deck page, list + detail views
- `crack_pack_server.py` — web server, route dispatch in
  `do_GET`/`do_POST`/`do_PUT`/`do_DELETE`
- `architecture/COMMANDER_DECK_TEMPLATE.md` — 99-card template
- `tag_all_cards.json` — 151 tags, 115k pairs, source of truth

### Existing infrastructure to reuse
- `DeckBuilderService.create_deck()` — commander validation + deck creation
- `DeckBuilderService.set_plan()` / `get_plan()` — plan storage
- `DeckBuilderService.audit_deck()` — category counts, gap analysis
- `DeckBuilderService._classify_card()` — tag-based card classification
- Collection page filter pattern — client-side, checkbox-driven
- SSE streaming — used by ingest processing, reuse for Claude plan generation
