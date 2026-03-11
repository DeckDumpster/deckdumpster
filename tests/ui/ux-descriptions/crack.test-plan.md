# Crack-a-Pack (`/crack`) -- Test Plan

**UX Description:** `tests/ui/ux-descriptions/crack.md`
**Page:** `/crack` (`mtg_collector/static/crack_pack.html`)
**Generated:** 2026-03-09

---

## 1. Existing Intents

| # | Filename | Summary |
|---|----------|---------|
| 1 | `crack_pack_normal_mode.yaml` | Open a pack with Surprise toggle unchecked. All cards appear face-up immediately with rarity-colored borders and treatment badges. Covers Flow 3 (Open Pack - Normal Mode). |
| 2 | `crack_pack_pick_cards.yaml` | Open a pack in normal mode, click cards to add them to the picks sidebar panel. Picked cards show a red glow, PICKED overlay badge, and appear in the picks panel with a count badge. Covers Flow 7 (Pick a Card). |
| 3 | `crack_pack_surprise_mode.yaml` | Open a pack in surprise mode (cards face-down), click individual cards to reveal them with flip animation, then click Reveal All to flip remaining cards. Covers Flow 4 (Surprise Mode), Flow 5 (Reveal Individual), Flow 6 (Reveal All). |

---

## 2. Proposed New Intents

### HIGH Priority

These cover core user flows and interactions not yet tested by existing intents.

#### 2.1 `crack_pack_initial_empty_state.yaml`

- **Description:** When I first load the Crack-a-Pack page, the set input shows "Loading sets..." and is disabled. After sets load, it changes to "Search sets..." and the status text shows "{N} sets loaded". The Open Pack, Reveal All, and Explore Sheets buttons are all disabled. The pack header reads "Select a set and open a pack", the grid is empty, and the picks panel shows "(0)" with the placeholder "Click cards to pick them".
- **Priority:** High
- **UX flows/states covered:** Visual States (Initial / Empty State, Sets Loaded State), Dynamic Behavior (On Page Load)
- **Testability notes:** Fully testable. All disabled states, placeholder texts, and button states are DOM-observable. The transition from "Loading sets..." to "Search sets..." happens asynchronously after the `/api/sets` call completes, so a brief wait may be needed.

#### 2.2 `crack_pack_set_search_filter.yaml`

- **Description:** I can type in the set search input to filter the dropdown list in real time. The dropdown shows matching sets by name or code (case-insensitive). I can use ArrowUp/ArrowDown to navigate the list and Enter to select. After selection, the input shows "{set name} ({set code})", the dropdown closes, product radio buttons appear, and the first product is auto-selected with a red highlight. The Open Pack and Explore Sheets buttons become enabled.
- **Priority:** High
- **UX flows/states covered:** Flow 1 (Select a Set), Flow 2 (Change Product Type -- product auto-selection), Visual States (Dropdown Open, Set Selected / Products Loading, Set Selected / Products Loaded), Dynamic Behavior (Set Search Dropdown, Product Radio Buttons)
- **Testability notes:** Fully testable. Dropdown filtering, keyboard navigation (ArrowUp/ArrowDown/Enter/Escape), and product radio button generation are all driven via Playwright. The dropdown visibility is controlled by the `open` class on `#set-dropdown`.

#### 2.3 `crack_pack_product_selection.yaml`

- **Description:** After selecting a set that has multiple product types (e.g., draft, collector, play), I can switch between products by clicking the pill-shaped radio labels. The selected product is highlighted with a red (#e94560) background. Opening a pack uses the currently selected product type, reflected in the pack header.
- **Priority:** High
- **UX flows/states covered:** Flow 2 (Change Product Type), Interactive Elements (Product radio buttons), Visual States (Set Selected / Products Loaded)
- **Testability notes:** Fully testable. Radio button checked state and label styling are DOM-observable. Verify the pack header reflects the selected product name after opening.

#### 2.4 `crack_pack_unpick_card.yaml`

- **Description:** After picking a card from an opened pack, I can click the same card again to unpick it. The red glow border and PICKED badge are removed from the card in the grid, the card is removed from the picks panel, and the pick count decreases.
- **Priority:** High
- **UX flows/states covered:** Flow 8 (Unpick a Card), Dynamic Behavior (Pick State Synchronization)
- **Testability notes:** Fully testable. Verify the `picked` class is removed from the card slot, the PICKED overlay disappears, the pick is removed from `#pick-list`, and `#pick-count` decrements.

#### 2.5 `crack_pack_clear_all_picks.yaml`

- **Description:** After picking several cards, I click the "Clear All" button in the picks panel. All picks are removed, the panel shows the empty state message "Click cards to pick them", the pick count resets to "(0)", and all PICKED overlays are removed from the pack grid. localStorage is cleared of picks data.
- **Priority:** High
- **UX flows/states covered:** Flow 10 (Clear All Picks), Interactive Elements (Clear All button), Visual States (Picks Panel empty state)
- **Testability notes:** Fully testable. Verify `#pick-list` is empty (or shows only the placeholder text), `#pick-count` shows "(0)", and no `.card-slot` elements have class `picked`.

#### 2.6 `crack_pack_zoom_card.yaml`

- **Description:** I can click the magnifying glass zoom badge on any face-up card to open a full-screen dark overlay showing a large card image (up to 85vh x 90vw). Clicking anywhere on the overlay closes it. The zoom badge click does not trigger pick toggling (event isolation via `stopPropagation`).
- **Priority:** High
- **UX flows/states covered:** Flow 11 (Zoom Into a Card), Interactive Elements (Zoom badge, Zoom overlay, Zoom image), Visual States (Zoom Overlay Active)
- **Testability notes:** Fully testable. Verify `#zoom-overlay` gains class `active` when a zoom badge is clicked, `#zoom-img` src matches the card's image, and the overlay loses `active` class on click. Also verify that clicking zoom on a face-down card has no effect.

#### 2.7 `crack_pack_url_hash_share.yaml`

- **Description:** After opening a pack, the URL hash automatically encodes set, product, seed, surprise mode, and revealed card indices (format: `#set=X&product=Y&seed=Z&surprise=0|1&revealed=0,1,...`). Loading a page with this hash deterministically regenerates the exact same pack with the same cards and reveal state. The set input, product radio, and surprise toggle all reflect the hash values.
- **Priority:** High
- **UX flows/states covered:** Flow 14 (Share/Restore a Pack via URL Hash), Dynamic Behavior (URL Hash State), Visual States (Hash-Restored State)
- **Testability notes:** Fully testable. Two-phase test: (1) open a pack, capture the URL hash; (2) navigate to the URL, verify the pack is identical. The deterministic seed ensures reproducibility. Requires the harness to support page navigation with a specific URL.

#### 2.8 `crack_pack_sequential_packs.yaml`

- **Description:** After opening a pack and picking some cards, I open another pack (same or different set/product). The new pack replaces the previous grid. Picks from the earlier pack persist in the picks sidebar. Cards in the new pack do not incorrectly show PICKED styling (different printing IDs and indices).
- **Priority:** High
- **UX flows/states covered:** Flow 16 (Open Multiple Packs Sequentially), Dynamic Behavior (Pick State Synchronization, Picks Panel Persistence)
- **Testability notes:** Fully testable. Open pack 1, pick a card, open pack 2. Verify: (a) picks panel still lists the prior pick, (b) no `.card-slot` in the new grid has class `picked`, (c) pick count remains accurate.

### MEDIUM Priority

These cover secondary flows, persistence, and deeper verification of already-partially-covered features.

#### 2.9 `crack_pack_set_search_reselect.yaml`

- **Description:** After selecting a set, clicking back into the set input clears the previous selection and reopens the full dropdown list. I can search for and select a different set. Product radios update to reflect the newly selected set's products.
- **Priority:** Medium
- **UX flows/states covered:** Flow 1 steps 3-4 (re-focus clears selection), Dynamic Behavior (Set Search Dropdown -- "On focus, if a set was previously selected, the input clears")
- **Testability notes:** Fully testable. Verify input value clears on focus, dropdown reopens with full list, and product radios regenerate after selecting a new set.

#### 2.10 `crack_pack_reveal_individual_cards.yaml`

- **Description:** After opening a pack in surprise mode, I click individual face-down cards to reveal them one at a time. Revealed cards show their image. Un-clicked cards remain face-down. The Reveal All button stays enabled while any cards are face-down. The URL hash updates to include each newly revealed card index.
- **Priority:** Medium
- **UX flows/states covered:** Flow 5 (Reveal Individual Cards), Visual States (Pack Open -- Partially Revealed), Dynamic Behavior (Card Flip Animation, URL Hash State)
- **Testability notes:** Fully testable. The existing `crack_pack_surprise_mode` covers this partially, but this intent focuses specifically on the partially-revealed intermediate state and URL hash updates per reveal. Verify the `face-down` class is removed only from clicked cards.

#### 2.11 `crack_pack_remove_pick_from_panel.yaml`

- **Description:** I can remove a specific pick by clicking the "x" button on a pick item in the sidebar panel. The card is removed from picks, the count updates, and if the card's pack is still displayed, the PICKED styling is removed from the corresponding card in the grid.
- **Priority:** Medium
- **UX flows/states covered:** Flow 9 (Remove a Pick from the Panel), Interactive Elements (Remove pick button)
- **Testability notes:** Fully testable. Click the `.remove-pick` span on a pick item. Verify the pick item is removed from `#pick-list`, `#pick-count` decrements, and the matching `.card-slot` loses the `picked` class.

#### 2.12 `crack_pack_grid_columns.yaml`

- **Description:** I can adjust the pack grid column count using the "-" and "+" buttons. The `#col-count` display updates, the grid re-layouts immediately via the `--grid-cols` CSS variable, and the preference persists across page reloads via localStorage key `crackPackGridCols`. The "-" button disables at 1 column; the "+" button disables at 12 columns.
- **Priority:** Medium
- **UX flows/states covered:** Flow 12 (Adjust Grid Column Count), Interactive Elements (Column minus/plus buttons, Column count display), Dynamic Behavior (Grid Column Persistence)
- **Testability notes:** Fully testable. Check button disabled states at boundaries, verify `#col-count` text, and inspect the `--grid-cols` CSS variable on `#pack-grid`. localStorage persistence can be verified with a page reload if the harness supports it.

#### 2.13 `crack_pack_navigate_explore_sheets.yaml`

- **Description:** After selecting a set and product, the Explore Sheets button becomes enabled. Clicking it navigates to `/sheets#set=X&product=Y` with the current set and product encoded in the URL hash.
- **Priority:** Medium
- **UX flows/states covered:** Flow 15 (Navigate to Explore Sheets), Interactive Elements (Explore Sheets button), Navigation (Explore Sheets button)
- **Testability notes:** Fully testable. Verify button enabled/disabled state transitions and the resulting navigation URL. The target page does not need to be fully rendered -- just verify the URL change.

#### 2.14 `crack_pack_pack_header_stats.yaml`

- **Description:** After opening a pack, the pack header displays statistics in the format: "{setCode} {product} -- {N} cards (variant {variantIndex}, {pct}%) -- ${total}". This includes the set code, product name, card count, variant index with weight percentage, and total pack value.
- **Priority:** Medium
- **UX flows/states covered:** Dynamic Behavior (Pack Header Statistics), Interactive Elements (Pack header)
- **Testability notes:** Fully testable. Parse `#pack-header` text content and verify it matches the expected format. The specific values depend on the generated pack but the format pattern is deterministic.

#### 2.15 `crack_pack_card_badges.yaml`

- **Description:** Cards in an opened pack display contextual badges below the image: a zoom magnifying glass, Scryfall (SF) link with optional TCGplayer price, Card Kingdom (CK) link with optional price (when CK data available), and treatment badges (BL/SC/EA/FA) based on card properties. Badge visibility depends on card data and the `price_sources` setting.
- **Priority:** Medium
- **UX flows/states covered:** Interactive Elements (SF badge, CK badge, Treatment badges, Zoom badge), Data Dependencies (Card Data Fields -- `border_color`, `frame_effects`, `is_full_art`, `tcg_price`, `ck_price`)
- **Testability notes:** Limited. Treatment badges (BL, SC, EA, FA) require the generated pack to contain cards with those specific properties, which depends on pack randomness and fixture data. SF/CK badges depend on price data availability. A pre-identified seed that produces known card treatments would improve reliability. The zoom badge is always present and fully testable.

#### 2.16 `crack_pack_url_hash_partial_reveal.yaml`

- **Description:** When I open a pack in surprise mode and reveal only some cards, the URL hash reflects the partially revealed state (only revealed indices in the `revealed` parameter). Loading the URL in a new session restores the pack with exactly those cards face-up and the rest face-down.
- **Priority:** Medium
- **UX flows/states covered:** Flow 14 (partial reveal via hash), Visual States (Pack Open -- Partially Revealed, Hash-Restored State), Dynamic Behavior (URL Hash State)
- **Testability notes:** Fully testable. Extends `crack_pack_url_hash_share` to specifically test the partial-reveal round-trip. Open in surprise mode, reveal 2-3 cards, capture hash, navigate to hash URL, verify the same cards are face-up and others face-down.

#### 2.17 `crack_pack_picks_persistence.yaml`

- **Description:** I pick several cards from a pack, reload the page, and the picks panel restores all previously picked cards from localStorage. The pick count, thumbnails, names, set/CN, and badges all reappear correctly in the picks panel after reload.
- **Priority:** Medium
- **UX flows/states covered:** Dynamic Behavior (Picks Panel Persistence, On Page Load -- `renderPicks()`), Data Dependencies (localStorage key `crackPackPicks`)
- **Testability notes:** Fully testable if the harness supports page reload/navigation. Pick cards, trigger a page reload via Playwright, then verify picks panel contents match. If reload is not supported, this intent cannot be implemented.

### LOW Priority

These cover edge cases, visual polish, and features with limited testability.

#### 2.18 `crack_pack_ck_prices_update.yaml`

- **Description:** The CK prices status text shows the age of Card Kingdom price data (e.g., "CK: 2h ago", "CK: not loaded"). Clicking it triggers a POST to `/api/fetch-prices`. The text changes to "CK: downloading..." in red during the request, then updates to a new timestamp on success or "CK: error" on failure.
- **Priority:** Low
- **UX flows/states covered:** Flow 13 (Update Card Kingdom Prices), Interactive Elements (CK prices status), Visual States (CK Prices Loading State, CK Prices Error State)
- **Testability notes:** **Limited testability.** The price download depends on external network access to Card Kingdom, which test containers typically lack. The "CK: downloading..." transient state may be too brief to capture via screenshot. Can verify: initial status text is present and clickable, and the click triggers the loading class. Cannot reliably verify success/error outcome.

#### 2.19 `crack_pack_foil_visual_effects.yaml`

- **Description:** When a pack contains foil cards, those cards display a rainbow color wash overlay (`::before` pseudo-element with repeating-linear-gradient) and an animated light streak (`::after` with `foil-streak` keyframes, 3s cycle). These effects are visible only when the card is face-up.
- **Priority:** Low
- **UX flows/states covered:** Dynamic Behavior (Foil Animation), Interactive Elements (Card front -- `foil` class)
- **Testability notes:** **Limited testability.** Foil effects are CSS pseudo-element animations only verifiable via screenshot/Vision comparison. Requires a pack containing at least one foil card, which depends on randomness and fixture data. The `foil` class on `.card-front` is DOM-observable, but the visual effect itself needs Vision. A known seed producing a foil card would be needed.

#### 2.20 `crack_pack_header_home_link.yaml`

- **Description:** The "Crack-a-Pack" header title is a styled link (`<a>` wrapping `<h1>`) that navigates to the homepage (`/`). It appears as plain text with `color:inherit; text-decoration:none`.
- **Priority:** Low
- **UX flows/states covered:** Navigation (Header title link)
- **Testability notes:** Fully testable. Simple check: verify the `<h1>` is wrapped in an `<a>` with `href="/"`. Trivial intent with minimal value.

---

## 3. Coverage Summary

| Category | Existing | Proposed | Total |
|----------|----------|----------|-------|
| Page load / initial state | 0 | 1 | 1 |
| Set selection & search | 0 | 2 | 2 |
| Product selection | 0 | 1 | 1 |
| Pack opening (normal) | 1 | 0 | 1 |
| Pack opening (surprise) | 1 | 0 | 1 |
| Card reveal (individual) | 0 | 1 | 1 |
| Pick management | 1 | 4 | 5 |
| Zoom overlay | 0 | 1 | 1 |
| Grid column controls | 0 | 1 | 1 |
| CK prices | 0 | 1 | 1 |
| URL hash sharing | 0 | 2 | 2 |
| Navigation | 0 | 2 | 2 |
| Pack header stats | 0 | 1 | 1 |
| Card badges & treatments | 0 | 1 | 1 |
| Foil visual effects | 0 | 1 | 1 |
| Sequential packs | 0 | 1 | 1 |
| Picks persistence | 0 | 1 | 1 |
| **TOTAL** | **3** | **20** | **23** |

---

## 4. Coverage Matrix

Maps each section of the UX description to the intents that cover it. Existing intents are marked `[E]`, proposed intents are marked `[P]`.

### Flows (Section 4)

| Flow | Description | Covered By |
|------|-------------|------------|
| Flow 1 | Select a Set | `[P] crack_pack_set_search_filter`, `[P] crack_pack_set_search_reselect` |
| Flow 2 | Change Product Type | `[P] crack_pack_product_selection`, `[P] crack_pack_set_search_filter` (auto-select) |
| Flow 3 | Open a Pack (Normal Mode) | `[E] crack_pack_normal_mode` |
| Flow 4 | Open a Pack (Surprise Mode) | `[E] crack_pack_surprise_mode` |
| Flow 5 | Reveal Individual Cards | `[E] crack_pack_surprise_mode`, `[P] crack_pack_reveal_individual_cards` |
| Flow 6 | Reveal All Cards | `[E] crack_pack_surprise_mode` |
| Flow 7 | Pick a Card | `[E] crack_pack_pick_cards` |
| Flow 8 | Unpick a Card | `[P] crack_pack_unpick_card` |
| Flow 9 | Remove a Pick from the Panel | `[P] crack_pack_remove_pick_from_panel` |
| Flow 10 | Clear All Picks | `[P] crack_pack_clear_all_picks` |
| Flow 11 | Zoom Into a Card | `[P] crack_pack_zoom_card` |
| Flow 12 | Adjust Grid Column Count | `[P] crack_pack_grid_columns` |
| Flow 13 | Update Card Kingdom Prices | `[P] crack_pack_ck_prices_update` |
| Flow 14 | Share/Restore via URL Hash | `[P] crack_pack_url_hash_share`, `[P] crack_pack_url_hash_partial_reveal` |
| Flow 15 | Navigate to Explore Sheets | `[P] crack_pack_navigate_explore_sheets` |
| Flow 16 | Open Multiple Packs Sequentially | `[P] crack_pack_sequential_packs` |

### Interactive Elements (Section 3)

| Element | ID/Selector | Covered By |
|---------|-------------|------------|
| Set search input | `set-input` | `[P] crack_pack_set_search_filter`, `[P] crack_pack_set_search_reselect` |
| Set dropdown | `set-dropdown` | `[P] crack_pack_set_search_filter` |
| Product radio buttons | `product-radios` | `[P] crack_pack_product_selection` |
| Open Pack button | `open-btn` | `[E] crack_pack_normal_mode`, `[E] crack_pack_surprise_mode` |
| Surprise mode toggle | `open-mode` | `[E] crack_pack_normal_mode`, `[E] crack_pack_surprise_mode` |
| Reveal All button | `reveal-all-btn` | `[E] crack_pack_surprise_mode`, `[P] crack_pack_reveal_individual_cards` |
| Explore Sheets button | `sheets-btn` | `[P] crack_pack_navigate_explore_sheets` |
| Column minus button | `col-minus` | `[P] crack_pack_grid_columns` |
| Column count display | `col-count` | `[P] crack_pack_grid_columns` |
| Column plus button | `col-plus` | `[P] crack_pack_grid_columns` |
| CK prices status | `prices-status` | `[P] crack_pack_ck_prices_update` |
| Status text | `status-text` | `[P] crack_pack_initial_empty_state` |
| Pack header | `pack-header` | `[P] crack_pack_pack_header_stats`, `[P] crack_pack_initial_empty_state` |
| Pack grid | `pack-grid` | `[E] crack_pack_normal_mode`, `[P] crack_pack_grid_columns` |
| Card slots | `.card-slot` | `[E] crack_pack_normal_mode`, `[E] crack_pack_surprise_mode`, `[E] crack_pack_pick_cards` |
| Card flip animation | `.face-down` toggle | `[E] crack_pack_surprise_mode`, `[P] crack_pack_reveal_individual_cards` |
| Foil effects | `.card-front.foil` | `[P] crack_pack_foil_visual_effects` |
| Zoom badge | `.badge.zoom-badge` | `[P] crack_pack_zoom_card` |
| SF badge | `a.badge.link` (SF) | `[P] crack_pack_card_badges` |
| CK badge | `a.badge.link` (CK) | `[P] crack_pack_card_badges` |
| Treatment badges | `.badge.treatment` | `[P] crack_pack_card_badges` |
| Zoom overlay | `zoom-overlay` | `[P] crack_pack_zoom_card` |
| Zoom image | `zoom-img` | `[P] crack_pack_zoom_card` |
| Pick count | `pick-count` | `[E] crack_pack_pick_cards`, `[P] crack_pack_clear_all_picks`, `[P] crack_pack_unpick_card` |
| Clear All button | `clear-picks` | `[P] crack_pack_clear_all_picks` |
| Pick list | `pick-list` | `[E] crack_pack_pick_cards`, `[P] crack_pack_clear_all_picks` |
| Pick items | `.pick-item` | `[E] crack_pack_pick_cards`, `[P] crack_pack_remove_pick_from_panel` |
| Remove pick button | `.remove-pick` | `[P] crack_pack_remove_pick_from_panel` |
| Header title link | `<a>` wrapping `<h1>` | `[P] crack_pack_header_home_link` |

### Visual States (Section 7)

| State | Covered By |
|-------|------------|
| Initial / Empty State | `[P] crack_pack_initial_empty_state` |
| Sets Loaded State | `[P] crack_pack_initial_empty_state`, `[P] crack_pack_set_search_filter` |
| Set Selected / Products Loading | `[P] crack_pack_set_search_filter` |
| Set Selected / Products Loaded | `[P] crack_pack_product_selection` |
| Pack Open -- Normal Mode (All Face-Up) | `[E] crack_pack_normal_mode` |
| Pack Open -- Surprise Mode (All Face-Down) | `[E] crack_pack_surprise_mode` |
| Pack Open -- Partially Revealed | `[P] crack_pack_reveal_individual_cards`, `[P] crack_pack_url_hash_partial_reveal` |
| Card Picked State | `[E] crack_pack_pick_cards` |
| Picks Panel -- With Picks | `[E] crack_pack_pick_cards`, `[P] crack_pack_picks_persistence` |
| Zoom Overlay Active | `[P] crack_pack_zoom_card` |
| CK Prices Loading State | `[P] crack_pack_ck_prices_update` |
| CK Prices Error State | `[P] crack_pack_ck_prices_update` |
| Dropdown Open State | `[P] crack_pack_set_search_filter` |
| Mobile / Responsive State | -- (not covered, out of scope) |
| Hash-Restored State | `[P] crack_pack_url_hash_share`, `[P] crack_pack_url_hash_partial_reveal` |
| Foil visual effects | `[P] crack_pack_foil_visual_effects` |

### Dynamic Behaviors (Section 5)

| Behavior | Covered By |
|----------|------------|
| On Page Load | `[P] crack_pack_initial_empty_state` |
| Set Search Dropdown filtering | `[P] crack_pack_set_search_filter` |
| Product Radio Buttons | `[P] crack_pack_product_selection` |
| Card Flip Animation | `[E] crack_pack_surprise_mode`, `[P] crack_pack_reveal_individual_cards` |
| Foil Animation | `[P] crack_pack_foil_visual_effects` |
| Rarity/Set Border Colors | `[E] crack_pack_normal_mode`, `[P] crack_pack_card_badges` |
| Pick State Synchronization | `[P] crack_pack_sequential_packs`, `[P] crack_pack_unpick_card` |
| URL Hash State | `[P] crack_pack_url_hash_share`, `[P] crack_pack_url_hash_partial_reveal` |
| Pack Header Statistics | `[P] crack_pack_pack_header_stats` |
| Picks Panel Persistence | `[P] crack_pack_picks_persistence`, `[P] crack_pack_sequential_packs` |
| Grid Column Persistence | `[P] crack_pack_grid_columns` |

---

## 5. Limited Testability Summary

| Proposed Intent | Limitation | Mitigation |
|-----------------|------------|------------|
| `crack_pack_ck_prices_update` | Price download POSTs to `/api/fetch-prices` which depends on external network access to Card Kingdom. Test containers typically lack outbound network. The "CK: downloading..." transient state may be too brief for screenshot capture. | Verify only the initial status text, the click interaction (loading class applied), and the text change to "CK: downloading...". Do not assert on success/error outcomes. Alternatively, mock the endpoint at the test level. |
| `crack_pack_foil_visual_effects` | Foil rainbow wash and light streak are CSS pseudo-element animations only verifiable via Claude Vision screenshot comparison. Requires a pack containing foil cards, which depends on random seed and fixture data. | Pre-identify a seed that produces at least one foil card in the test fixture. Assert the `foil` class on `.card-front` as a DOM check, then use Vision for the visual effect. |
| `crack_pack_card_badges` | Treatment badges (BL, SC, EA, FA) require generated packs containing cards with `border_color: "borderless"`, `frame_effects: ["showcase"]`/`["extendedart"]`, or `is_full_art: true`. Depends on fixture data and pack randomness. | Pre-identify seeds that produce cards with known treatments in the test fixture. SF/CK price badges depend on price data being loaded. |
| `crack_pack_picks_persistence` | Verifying localStorage persistence requires a page reload within the test. If the harness does not support `page.reload()` or navigation, this intent cannot be fully tested. | Confirm harness supports page reload before implementing. If not, defer or mark as manual-only. |
| **Mobile / Responsive** (not proposed) | Requires viewport resize to <=768px, layout reflow verification (vertical stack vs side-by-side), picks panel repositioning (top border vs left border). Vision-based layout assertions unreliable for subtle CSS changes. | Out of scope for intent-based tests. Could be covered by dedicated responsive screenshot comparisons if needed. |
