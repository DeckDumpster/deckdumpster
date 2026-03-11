# Deck Detail Page

**URL:** `/decks/:id` (e.g., `/decks/1`)
**Source HTML:** `mtg_collector/static/deck_detail.html`
**Source JS:** `mtg_collector/static/deck-detail.js`
**Source CSS:** `mtg_collector/static/deck-detail.css`
**Shared assets:** `mtg_collector/static/shared.css`, `mtg_collector/static/shared.js`
**Served by:** `crack_pack_server.py` route `path.startswith("/decks/")` -> serves `deck_detail.html`

---

## 1. Page Purpose

The Deck Detail page is a standalone view for a single deck, reached by navigating to `/decks/:id`. It shows the deck's full metadata (name, format, precon status, sleeves, deck box, storage location, description, card count, total value), a tabbed card table organized by zone (Mainboard, Sideboard, Commander), and a collapsible completeness tracking section that compares actual cards against an expected card list. Users can edit deck properties, add cards from their collection, remove cards, import an expected card list, track completeness with "present/missing/extra" categorization, reassemble unassigned cards back into the deck, and delete the deck entirely. The page title is dynamically set to "{deck name} -- DeckDumpster".

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "DeckDumpster" in `.site-header h1` | Link | `/` | Home page link, styled with accent color |
| "Collection" | Link in `.site-header` | `/collection` | Global nav |
| "Decks" | Link in `.site-header` | `/decks` | Global nav, links back to decks list |
| "Binders" | Link in `.site-header` | `/binders` | Global nav |
| "Sealed" | Link in `.site-header` | `/sealed` | Global nav |
| Card name in table | `<a>` per card row | `/card/:set/:cn` (e.g., `/card/fdn/132`) | Links to standalone card detail page; set code is lowercased |

**Header structure:** Uses the shared `.site-header` component (from `shared.css`) with full site navigation, unlike the legacy decks list page.

---

## 3. Interactive Elements

### Action Buttons (in `.deck-detail-header .actions`)

| Element | ID | Type | CSS Class | Action |
|---------|-----|------|-----------|--------|
| Edit button | `#btn-edit` | `<button>` | `secondary` | Opens the Edit Deck modal (`showEditModal()`) |
| Add Cards button | `#btn-add-cards` | `<button>` | (primary) | Opens the Add Cards picker modal (`showAddCardsModal()`) |
| Remove Selected button | `#btn-remove-selected` | `<button>` | `secondary` | Removes checked cards from the deck (`removeSelectedCards()`) |
| Import Expected List button | `#btn-import-expected` | `<button>` | `secondary` | Opens the Expected List import modal (`showExpectedModal()`) |
| Delete Deck button | `#btn-delete` | `<button>` | `danger` | Deletes the deck after confirmation prompt (`deleteDeck()`) |

### Zone Tabs (`#zone-tabs`)

| Element | Selector | Type | Action |
|---------|----------|------|--------|
| Mainboard tab | `.tab[data-zone="mainboard"]` | `<div>` | Switches to mainboard zone view; shows count as "(N)" in `#count-mainboard` |
| Sideboard tab | `.tab[data-zone="sideboard"]` | `<div>` | Switches to sideboard zone view; shows count as "(N)" in `#count-sideboard` |
| Commander tab | `.tab[data-zone="commander"]` | `<div>` | Switches to commander zone view; shows count as "(N)" in `#count-commander` |

### Card Table (`#card-table`)

| Element | ID/Selector | Type | Action |
|---------|------------|------|--------|
| Select All checkbox | `#select-all` | `<input type="checkbox">` | Toggles selection of all cards in the current zone |
| Per-card checkbox | `input[type="checkbox"][data-id]` in each row | `<input type="checkbox">` | Toggles selection of individual card; stores ID in `selectedCardIds` Set |
| Card name link | `<a href="/card/:set/:cn">` in each row | `<a>` | Navigates to card detail page |

**Table columns:** Checkbox, Name (linked), Set (uppercase code + #collector_number), Mana (rendered with mana-font icons via `renderMana()`), Type, Finish, Condition.

### Completeness Section (`#completeness-section`)

| Element | ID/Selector | Type | Action |
|---------|------------|------|--------|
| Completeness header | `#completeness-header` | `<div>` | Click toggles expand/collapse of the completeness body |
| Completeness toggle arrow | `#completeness-toggle` | `<span>` | Shows down arrow (expanded) or right arrow (collapsed) |
| Completeness summary | `#completeness-summary` | `<span>` | Displays "(X/Y present, Z missing, W extra)" text |
| Location tags | `.location-tag[data-cid]` | `<span>` | Clickable tags on missing cards showing where copies exist (Deck, Binder, or Unassigned). Click reassembles that card into this deck |
| Reassemble All button | `#btn-reassemble-all` | `<button>` | Dynamically created when unassigned missing cards exist. Reassembles all unassigned copies at once |

### Edit Deck Modal (`#deck-modal`)

| Element | ID | Type | Placeholder/Options | Validation |
|---------|-----|------|---------------------|------------|
| Modal title | `#modal-title` | `<h3>` | Always "Edit Deck" (this page is always editing) | -- |
| Name input | `#f-name` | `<input type="text">` | "My Commander Deck" | Required (JS alert if empty) |
| Format dropdown | `#f-format` | `<select>` | Options: `""` (None), `commander` (Commander / EDH), `standard`, `modern`, `pioneer`, `legacy`, `vintage`, `pauper` | Optional |
| Description textarea | `#f-description` | `<textarea rows="2">` | -- | Optional |
| Precon checkbox | `#f-precon` | `<input type="checkbox">` | -- | Toggles precon fields visibility via `change` event |
| Origin Set dropdown | `#f-origin-set` | `<select>` | Options: `""` (None), `jmp` (Jumpstart), `j22` (Jumpstart 2022), `j25` (Jumpstart 2025) | Only visible when precon checked |
| Theme input | `#f-origin-theme` | `<input type="text">` | "e.g. Goblins, Angels" | Only visible when precon checked |
| Variation input | `#f-origin-variation` | `<input type="number" min="1" max="4">` | "1-4" | Only visible when precon checked |
| Sleeve Color input | `#f-sleeve` | `<input type="text">` | "e.g. black dragon shield matte" | Optional |
| Deck Box input | `#f-deckbox` | `<input type="text">` | "e.g. Ultimate Guard Boulder 100+" | Optional |
| Storage Location input | `#f-location` | `<input type="text">` | "e.g. shelf 2, left side" | Optional |
| Save button | `#btn-save-deck` | `<button>` | -- | Calls `saveDeck()`, sends `PUT /api/decks/:id` |
| Cancel button | `#btn-cancel-edit` | `<button class="secondary">` | -- | Closes the modal |

### Add Cards Modal (`#add-cards-modal`)

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Zone dropdown | `#add-zone` | `<select>` | Options: `mainboard`, `sideboard`, `commander` |
| Search input | `#picker-search` | `<input type="text">` | Placeholder: "Search by name...", fires `searchPickerCards()` on every `input` event |
| Card picker results | `#picker-cards` | `<div class="picker-cards">` | Scrollable div (max-height 300px) showing search results |
| Individual picker card | `.picker-card[data-key]` | `<div>` | Click toggles selection (adds/removes `.selected` class). Key format: `{printing_id}|{finish}` |
| Add Selected button | `#btn-add-picker` | `<button>` | Calls `addSelectedPickerCards()` |
| Cancel button | `#btn-cancel-add` | `<button class="secondary">` | Closes the modal |

### Expected List Import Modal (`#expected-modal`)

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Decklist textarea | `#f-expected-list` | `<textarea rows="10">` | Placeholder: "1 Goblin Bushwhacker (ZEN) 125\n1 Raging Goblin (M10) 153\n6 Mountain (JMP) 62" |
| Error display | `#expected-errors` | `<div>` | Red text (#e74c3c), shows import parse errors and details |
| Import button | `#btn-import-expected-confirm` | `<button>` | Calls `importExpectedList()` |
| Cancel button | `#btn-cancel-expected` | `<button class="secondary">` | Closes the modal |

---

## 4. User Flows

### Flow 1: View Deck Detail (Page Load)

1. User navigates to `/decks/:id` (typically by clicking a deck card on the decks list page)
2. The HTML loads with a loading state: spinner and "Loading deck..." text inside `#loading-state`
3. `deck-detail.js` IIFE executes immediately
4. The deck ID is extracted from the URL path by splitting on `/` and taking the second segment
5. `GET /api/decks/:id` is fetched
6. If the response is not OK (e.g., 404): an error message is shown in place of the loading state ("Deck not found" or server error message)
7. If successful: the page title is set to "{deck name} -- DeckDumpster"
8. The entire page layout is built by replacing `#deck-detail-layout` innerHTML with the full DOM structure (header, zone tabs, card table, completeness section, all three modals)
9. All event listeners are wired up (zone tabs, buttons, checkboxes, modal interactions)
10. `renderDeckDetail()` populates the deck name, metadata grid, and triggers `loadCompleteness()`
11. `switchZone('mainboard')` is called, which clears selections, highlights the Mainboard tab, and calls `loadDeckCards()`
12. `loadDeckCards()` fetches `GET /api/decks/:id/cards`, counts cards per zone, updates zone tab counts, filters to current zone, and renders the card table

### Flow 2: Switch Between Zones

1. User clicks a zone tab (Mainboard, Sideboard, or Commander)
2. `switchZone(zone)` is called
3. `currentZone` is updated, `selectedCardIds` is cleared, the "Select All" checkbox is unchecked
4. The clicked tab gets the `.active` class; all others lose it
5. `loadDeckCards()` re-fetches all cards for the deck, re-counts per zone, filters to the selected zone
6. The card table body is re-rendered with only cards matching the selected zone
7. If no cards in the zone: a single row is shown with "No cards in this zone" centered text

### Flow 3: Select and Remove Cards

1. User checks individual card checkboxes or uses the "Select All" checkbox at the top of the table
2. Each checkbox toggle updates the `selectedCardIds` Set
3. "Select All" adds or removes all card IDs for the current zone
4. User clicks "Remove Selected" button
5. If no cards are selected: `alert('No cards selected')` is shown
6. If cards are selected: `DELETE /api/decks/:id/cards` is called with `{collection_ids: [...]}`
7. `selectedCardIds` is cleared
8. The deck data is re-fetched (`GET /api/decks/:id`), the detail header is re-rendered, and the card table is reloaded
9. Cards are unassigned from the deck (not deleted from collection)

### Flow 4: Edit Deck Properties

1. User clicks "Edit" button
2. `showEditModal()` populates all form fields with the current deck data
3. If the deck is a precon, the precon fields section is visible with origin set, theme, and variation pre-filled
4. The `#deck-modal` is shown (`.active` class added)
5. User modifies any fields
6. User clicks "Save"
7. `saveDeck()` validates name is non-empty, then sends `PUT /api/decks/:id` with the form data
8. On success: the modal closes, `deck` variable is updated with the response, `renderDeckDetail()` refreshes the header and metadata
9. Alternatively, user clicks "Cancel", presses the backdrop, to close without saving

### Flow 5: Add Cards from Collection

1. User clicks "Add Cards" button
2. `showAddCardsModal()` clears previous selections and search, shows the modal
3. The picker area shows: "Type to search your collection..."
4. User types in the search input
5. With fewer than 2 characters: message shows "Type at least 2 characters..."
6. With 2+ characters: `GET /api/collection?q={query}&status=owned` is fetched on every keystroke
7. Results are rendered as clickable `.picker-card` elements showing: card name, set code + collector number + finish, quantity owned
8. User clicks card entries to toggle selection (`.selected` class toggles, key added/removed from `pickerSelected` Set)
9. User optionally selects a zone from the dropdown (default: mainboard)
10. User clicks "Add Selected"
11. For each selected printing, `GET /api/collection/copies?printing_id={id}&finish={finish}` is fetched to get individual copy IDs
12. Only unassigned copies (no `deck_id` and no `binder_id`) are included
13. If no unassigned copies found: `alert('No unassigned copies found for the selected cards')` is shown
14. Otherwise: `POST /api/decks/:id/cards` is called with `{collection_ids: [...], zone: "..."}`
15. If API returns error: shown via `alert()`
16. On success: modal closes, deck data and card table are refreshed

### Flow 6: Import Expected Card List

1. User clicks "Import Expected List" button
2. `showExpectedModal()` clears the textarea and errors, shows the modal
3. User pastes a decklist in the format: `1 Goblin Bushwhacker (ZEN) 125` (one card per line)
4. User clicks "Import"
5. If textarea is empty: `alert('Paste a decklist first')` is shown
6. `POST /api/decks/:id/expected` is called with `{decklist: "..."}` (the raw textarea text)
7. If API returns error: error text (and optional details array) is displayed in `#expected-errors` in red
8. On success: modal closes, `loadCompleteness()` is called to refresh the completeness section

### Flow 7: View Completeness Tracking

1. Completeness is loaded automatically when the page renders (`renderDeckDetail()` calls `loadCompleteness()`)
2. `GET /api/decks/:id/expected` is fetched to check if an expected list exists
3. If no expected list and deck is not a precon: completeness section remains hidden (`display: none`)
4. If no expected list but deck is a precon: section is shown with "(no expected list set)" message and guidance to use "Import Expected List"
5. If expected list exists: `GET /api/decks/:id/completeness` is fetched
6. Summary line shows: "(X/Y present, Z missing, W extra)"
7. The body is divided into three groups:
   - **Present** (green header): cards that are in the deck, showing actual_qty/expected_qty and card name
   - **Missing** (red header): cards expected but not (fully) in the deck, with quantity info and clickable location tags
   - **Extra** (gray header): cards in the deck that are not in the expected list, showing "xN" quantity
8. User can click the completeness header to toggle expand/collapse

### Flow 8: Reassemble Missing Cards

1. In the Missing section of completeness, each missing card shows location tags indicating where copies exist
2. Tags are color-coded: green (`.unassigned`) for unassigned copies, dark blue for copies in other decks/binders
3. Clicking an individual "Unassigned" location tag calls `reassembleCard(collectionId)`: `POST /api/decks/:id/reassemble` with that single collection ID
4. If there are multiple unassigned copies across missing cards, a "Reassemble N Unassigned Cards" button appears
5. Clicking this button calls `reassembleAll()`: re-fetches completeness data, collects all unassigned IDs, sends them all in one `POST /api/decks/:id/reassemble` call
6. After reassembly: deck data is re-fetched, header and card table are refreshed, completeness is recalculated

### Flow 9: Delete Deck

1. User clicks "Delete Deck" button (red/danger styled)
2. A browser `confirm()` dialog appears: 'Delete "{deck name}"? Cards will be unassigned but not deleted.'
3. If user cancels: nothing happens
4. If user confirms: `DELETE /api/decks/:id` is called
5. On success: `window.location.href = '/decks'` redirects to the decks list page
6. Cards that were in the deck are unassigned (returned to unassigned pool) but not deleted from the collection

### Flow 10: Close Any Modal

1. User can close any of the three modals by:
   - Clicking the modal's Cancel button (removes `.active` from the backdrop)
   - Clicking the dark backdrop area outside the modal content (event listener checks `e.target === el`)
2. The modal disappears and no data changes are made

---

## 5. Dynamic Behavior

### Page Initialization (IIFE in `deck-detail.js`)

The entire page logic is wrapped in an immediately-invoked async function. The sequence is:
1. Extract deck ID from URL path (`/decks/:id`)
2. Validate URL format; show error if invalid
3. Fetch deck data from API
4. Show error state if deck not found
5. Replace the loading state with the full page structure (header, tabs, table, completeness, modals) -- all injected as innerHTML
6. Wire up all event listeners via `addEventListener()` (not inline `onclick`)
7. Call `renderDeckDetail()` and `switchZone('mainboard')` to populate initial content

### Mana Cost Rendering

Card mana costs are rendered using the `renderMana()` function from `shared.js`, which converts `{U}{B}{1}` format strings into `<i class="ms ms-u ms-cost ms-shadow"></i>` elements using the mana-font CSS library (loaded via CDN).

### Card Name Links

Each card name in the table is rendered as a link to `/card/:set/:cn` where `set` is the lowercased set code and `cn` is the collector number. This links to the standalone Card Detail page.

### Zone Tab Counts

Zone tabs show the count of cards in each zone as "(N)" next to the zone name. These counts are updated every time `loadDeckCards()` runs. The counts reflect ALL cards in the deck, not just the currently displayed zone.

### Completeness Body Toggle

The completeness section body can be collapsed/expanded by clicking its header. The toggle arrow changes between down-pointing (expanded) and right-pointing (collapsed). The `.collapsed` CSS class applies `display: none`.

### Dynamic Button in Completeness

The "Reassemble N Unassigned Cards" button is dynamically created inside the completeness body HTML only when unassigned copies exist among missing cards. Its event listener is attached after the HTML is injected.

### Picker Card Search (Debounce-free)

The card picker search fires on every `input` event with no debounce. Each keystroke beyond the 2-character minimum triggers an API call to `/api/collection?q=...&status=owned`. This could result in rapid successive API calls during fast typing.

### Modal Backdrop Click Dismissal

All three modal backdrops (`.modal-backdrop`) have click event listeners that check if the click target is the backdrop itself (not the modal content inside). If so, the `.active` class is removed, closing the modal.

### External CSS/Font Dependencies

The page loads three external CSS resources via CDN:
- `keyrune` -- MTG set symbol icon font (referenced but not actively used on this page)
- `mana-font` -- Mana symbol icon font (used by `renderMana()` for mana cost display)
- These are loaded from `cdn.jsdelivr.net` and require network access

---

## 6. Data Dependencies

### API Endpoints Used

| Method | Endpoint | When Called | Request Body | Response Shape |
|--------|----------|------------|--------------|----------------|
| `GET` | `/api/decks/:id` | Page load, after save/delete/add/remove cards, after reassemble | -- | `{id, name, description, format, is_precon, sleeve_color, deck_box, storage_location, origin_set_code, origin_theme, origin_variation, created_at, updated_at, card_count, total_value}` |
| `GET` | `/api/decks/:id/cards` | `loadDeckCards()` on page load and after any card changes | -- | `[{id, printing_id, finish, condition, language, purchase_price, acquired_at, deck_zone, set_code, collector_number, rarity, artist, image_uri, frame_effects, border_color, full_art, promo, promo_types, finishes, name, type_line, mana_cost, cmc, colors, color_identity, oracle_id, set_name}, ...]` |
| `GET` | `/api/decks/:id/expected` | `loadCompleteness()` on page load and after importing expected list | -- | `[{oracle_id, name, qty}, ...]` or `[]` |
| `GET` | `/api/decks/:id/completeness` | `loadCompleteness()` when expected list exists | -- | `{present: [{name, actual_qty, expected_qty}], missing: [{name, actual_qty, expected_qty, locations: [{collection_id, deck_name, binder_name}]}], extra: [{oracle_id, name, zone, actual_qty}]}` |
| `PUT` | `/api/decks/:id` | `saveDeck()` (edit) | `{name, format, description, is_precon, sleeve_color, deck_box, storage_location, origin_set_code, origin_theme, origin_variation}` | Updated deck object |
| `DELETE` | `/api/decks/:id` | `deleteDeck()` | -- | -- |
| `POST` | `/api/decks/:id/cards` | `addSelectedPickerCards()` | `{collection_ids: [int, ...], zone: string}` | `{added: int}` or `{error: string}` |
| `DELETE` | `/api/decks/:id/cards` | `removeSelectedCards()` | `{collection_ids: [int, ...]}` | -- |
| `POST` | `/api/decks/:id/expected` | `importExpectedList()` | `{decklist: string}` | `{imported: int}` or `{error: string, details: [string]}` |
| `POST` | `/api/decks/:id/reassemble` | `reassembleCard()` and `reassembleAll()` | `{collection_ids: [int, ...]}` | `{moved: int}` or `{error: string}` |
| `GET` | `/api/collection?q=...&status=owned` | `searchPickerCards()` in add cards modal | -- | `{cards: [{name, set_code, collector_number, finish, printing_id, qty}, ...]}` or `[...]` |
| `GET` | `/api/collection/copies?printing_id=...&finish=...` | `addSelectedPickerCards()` for each selected printing | -- | `[{id, deck_id, binder_id, ...}, ...]` |

### Required Data for Page to Function
- A valid deck must exist with the given ID; otherwise an error state is shown
- The deck cards endpoint must be reachable to populate the zone tabs and card table
- The collection must have cards for the add-cards picker to find results
- The expected list must be imported before completeness tracking is functional
- The mana-font CDN must be reachable for mana cost icons to render (graceful degradation: shows raw icon class names)

---

## 7. Visual States

### State 1: Loading

- The page shows a centered loading state: an animated spinner (CSS keyframe rotation) and "Loading deck..." text
- This is the initial state visible in the HTML before JS executes
- Lasts from page load until the deck API response arrives

### State 2: Error -- Invalid URL

- If the URL path doesn't match `/decks/:id` format (e.g., `/decks/` with no ID)
- The loading state is replaced with an `.empty-state` div showing "Invalid deck URL. Expected /decks/:id"

### State 3: Error -- Deck Not Found

- If `GET /api/decks/:id` returns a non-OK status (404, 500, etc.)
- The loading state is replaced with an `.empty-state` div showing the error message (e.g., "Deck not found")

### State 4: Loaded -- Deck with Cards

- Header shows deck name (large, accent-colored) and metadata grid with label/value pairs
- Five action buttons visible: Edit, Add Cards, Remove Selected, Import Expected List, Delete Deck
- Zone tabs show with counts: e.g., "Mainboard (8)", "Sideboard (3)", "Commander (0)"
- Active zone tab is highlighted in accent color; inactive tabs are dark with muted text
- Card table shows rows with: checkbox, linked card name, set code + number, mana cost (rendered as icons), type line, finish, condition
- Table rows highlight subtly on hover

### State 5: Loaded -- Deck with Empty Zone

- Same as State 4 for the header
- The selected zone tab is active but the table body shows a single centered row: "No cards in this zone"
- Other zone tabs still show their respective counts

### State 6: Loaded -- Deck with No Cards at All

- All three zone tabs show "(0)"
- Card table shows "No cards in this zone" for every tab

### State 7: Completeness Section Hidden

- When no expected list exists and the deck is not a precon
- The `#completeness-section` has `display: none`
- No visual element appears below the card table

### State 8: Completeness -- No Expected List (Precon)

- Section is visible with header "Expected Cards (no expected list set)"
- Body shows guidance text: "Use 'Import Expected List' to define the expected cards for this deck."

### State 9: Completeness -- Full Tracking

- Section header shows summary: "(X/Y present, Z missing, W extra)"
- Body is divided into up to three groups:
  - **Present** group: green "PRESENT (N)" header, cards listed with qty ratios (e.g., "2/2")
  - **Missing** group: red "MISSING (N)" header, cards with qty ratios and clickable location tags (green for unassigned, dark for assigned elsewhere)
  - **Extra** group: gray "EXTRA (N)" header, cards with "xN" quantities
- If unassigned missing cards exist: a "Reassemble N Unassigned Cards" button appears between Missing and Extra groups

### State 10: Completeness -- Collapsed

- Only the header bar is visible: "Expected Cards (X/Y present, Z missing, W extra)"
- The toggle arrow points right instead of down
- Body content is hidden via `.collapsed` class

### State 11: Edit Modal Open

- Dark backdrop overlay covers the page
- Modal shows "Edit Deck" title
- All fields pre-populated with current deck values
- If deck is a precon, the precon fields section is expanded

### State 12: Add Cards Modal -- Initial

- Dark backdrop overlay
- Modal shows "Add Cards to Deck" title
- Zone dropdown defaults to "Mainboard"
- Search input is empty
- Picker area shows "Type to search your collection..."

### State 13: Add Cards Modal -- Searching

- User has typed 2+ characters
- Picker area shows matching cards from collection
- Each card row shows: name, set+number+finish, quantity
- Selected cards have a pink/accent background highlight (`.selected` class)

### State 14: Add Cards Modal -- No Results

- User has typed a search query that matches nothing
- Picker area shows "No matching cards found"

### State 15: Expected Import Modal

- Dark backdrop overlay
- Large textarea for pasting decklist
- Error area below textarea (empty initially, red text on errors)
- Import and Cancel buttons

### State 16: Expected Import Modal -- With Errors

- Same as State 15 but the `#expected-errors` div shows red error text
- May include multiple lines if `result.details` array exists

### State 17: Confirm Delete Dialog

- Browser-native `confirm()` dialog appears over the page
- Message: 'Delete "{deck name}"? Cards will be unassigned but not deleted.'
- OK proceeds with deletion; Cancel dismisses
