# Decks List Page

**URL:** `/decks`
**Source:** `mtg_collector/static/decks.html`
**Served by:** `crack_pack_server.py` route `path == "/decks"` -> serves `decks.html`

---

## 1. Page Purpose

The Decks List page is the entry point for deck management in DeckDumpster. It displays all user-created decks as a responsive card grid, showing each deck's name, format, precon status, storage location, description, card count, and total value. Users can create new decks from this page by clicking "New Deck" to open a modal form. Clicking any deck card navigates to the standalone Deck Detail page (`/decks/:id`). This page also contains an embedded detail view (hidden by default, toggled via JS) that was the original inline deck viewer before the standalone detail page was created -- the list view is the default active view on page load.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| `<a href="/">MTG</a>` in `<h1>` | Link in header | `/` (home page) | Site logo/brand link; styled as accent color |
| Deck card (entire `.deck-card` element) | `<a>` link wrapping the card | `/decks/{id}` | Each deck in the grid is a clickable link to the standalone deck detail page |

**Note:** This page uses a legacy header (`<header>` element, not `.site-header`) with the text "MTG / Decks". It does not have the full site navigation bar (Collection, Decks, Binders, Sealed) that newer pages like Deck Detail use.

---

## 3. Interactive Elements

### Header Controls (List View) -- `#list-controls`

| Element | ID/Selector | Type | Action |
|---------|------------|------|--------|
| New Deck button | `button` inside `#list-controls` | `<button>` | Calls `showCreateModal()` -- opens the deck creation modal |

### Header Controls (Detail View) -- `#detail-controls` (hidden by default)

These controls are part of the legacy inline detail view and are hidden when the list view is active. They become visible if `showDeck()` is called (which sets `detail-controls` to visible). With the standalone deck detail page now in use, these may not be reachable through normal navigation.

| Element | ID/Selector | Type | Action |
|---------|------------|------|--------|
| Back to Decks button | `button.secondary` | `<button>` | Calls `showList()` -- switches back to list view |
| Add Cards button | `button` | `<button>` | Calls `showAddCardsModal()` -- opens add cards picker |
| Remove Selected button | `button.secondary` | `<button>` | Calls `removeSelectedCards()` -- removes checked cards from deck |
| Import Expected List button | `button.secondary` | `<button>` | Calls `showExpectedModal()` -- opens expected list import modal |

### Status indicator

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Status text | `#status` | `<span>` | Positioned at far right of header with `margin-left: auto`. Not actively written to by current JS. |

### Create/Edit Deck Modal -- `#deck-modal`

| Element | ID | Type | Placeholder/Options | Validation |
|---------|-----|------|---------------------|------------|
| Modal title | `#modal-title` | `<h3>` | Dynamically set to "New Deck" or "Edit Deck" | -- |
| Name input | `#f-name` | `<input type="text">` | "My Commander Deck" | Required (JS alert if empty) |
| Format dropdown | `#f-format` | `<select>` | Options: `""` (None), `commander`, `standard`, `modern`, `pioneer`, `legacy`, `vintage`, `pauper` | Optional |
| Description textarea | `#f-description` | `<textarea rows="2">` | -- | Optional |
| Precon checkbox | `#f-precon` | `<input type="checkbox">` | -- | Toggles precon fields visibility |
| Origin Set dropdown | `#f-origin-set` | `<select>` | Options: `""` (None), `jmp` (Jumpstart), `j22` (Jumpstart 2022), `j25` (Jumpstart 2025) | Only visible when precon checked |
| Theme input | `#f-origin-theme` | `<input type="text">` | "e.g. Goblins, Angels" | Only visible when precon checked |
| Variation input | `#f-origin-variation` | `<input type="number" min="1" max="4">` | "1-4" | Only visible when precon checked |
| Sleeve Color input | `#f-sleeve` | `<input type="text">` | "e.g. black dragon shield matte" | Optional |
| Deck Box input | `#f-deckbox` | `<input type="text">` | "e.g. Ultimate Guard Boulder 100+" | Optional |
| Storage Location input | `#f-location` | `<input type="text">` | "e.g. shelf 2, left side" | Optional |
| Save button | (no ID) | `<button>` | -- | Calls `saveDeck()` |
| Cancel button | (no ID) | `<button class="secondary">` | -- | Calls `closeModal('deck-modal')` |

### Add Cards Modal -- `#add-cards-modal` (legacy inline detail view)

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Zone dropdown | `#add-zone` | `<select>` | Options: `mainboard`, `sideboard`, `commander` |
| Search input | `#picker-search` | `<input type="text">` | Placeholder: "Search by name...", fires `searchPickerCards()` on input |
| Card picker results | `#picker-cards` | `<div class="picker-cards">` | Scrollable list, max-height 300px |
| Add Selected button | (no ID) | `<button>` | Calls `addSelectedPickerCards()` |
| Cancel button | (no ID) | `<button class="secondary">` | Calls `closeModal('add-cards-modal')` |

### Expected List Import Modal -- `#expected-modal` (legacy inline detail view)

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Decklist textarea | `#f-expected-list` | `<textarea rows="10">` | Placeholder shows format: "1 Goblin Bushwhacker (ZEN) 125" |
| Error display | `#expected-errors` | `<div>` | Red text, shows import errors |
| Import button | (no ID) | `<button>` | Calls `importExpectedList()` |
| Cancel button | (no ID) | `<button class="secondary">` | Calls `closeModal('expected-modal')` |

### Legacy Inline Detail View Elements (normally hidden)

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Deck name heading | `#deck-name` | `<h2>` | Populated by `renderDeckDetail()` |
| Deck metadata grid | `#deck-meta` | `<div class="meta-grid">` | Grid of label/value pairs |
| Edit button | `button.secondary` in `.actions` | `<button>` | Calls `showEditModal()` |
| Delete Deck button | `button.danger` in `.actions` | `<button>` | Calls `deleteDeck()` with confirmation |
| Zone tabs (Mainboard) | `.tab[data-zone="mainboard"]` | `<div>` | Calls `switchZone('mainboard')` |
| Zone tabs (Sideboard) | `.tab[data-zone="sideboard"]` | `<div>` | Calls `switchZone('sideboard')` |
| Zone tabs (Commander) | `.tab[data-zone="commander"]` | `<div>` | Calls `switchZone('commander')` |
| Zone count spans | `#count-mainboard`, `#count-sideboard`, `#count-commander` | `<span>` | Populated with "(N)" format |
| Select All checkbox | `#select-all` | `<input type="checkbox">` | Calls `toggleSelectAll(this)` |
| Card table body | `#card-tbody` | `<tbody>` | Rows rendered by `renderCards()` |
| Completeness section | `#completeness-section` | `<div>` | Hidden by default, shown when expected list exists |
| Completeness toggle | `#completeness-toggle` | `<span>` | Arrow character, toggles body visibility |
| Completeness summary | `#completeness-summary` | `<span>` | Text like "(X/Y present, Z missing, W extra)" |
| Completeness body | `#completeness-body` | `<div>` | Rendered completeness cards with location tags |

---

## 4. User Flows

### Flow 1: View Deck List (Default)

1. User navigates to `/decks`
2. Page loads and immediately calls `loadDecks()` which fetches `GET /api/decks`
3. If decks exist: a responsive grid of deck cards is rendered in `#deck-grid`, each showing name, format badge, precon badge (if applicable), storage location, description, card count, and total value
4. If no decks exist: the `#empty-state` div is shown with text "No decks yet. Click 'New Deck' to create one."
5. User sees each deck as a clickable card in a grid layout

### Flow 2: Navigate to Deck Detail

1. User clicks on any deck card in the grid
2. Browser navigates to `/decks/{id}` (standard link navigation, not JS-driven)
3. The Deck Detail standalone page loads (see `deck-detail.md`)

### Flow 3: Create a New Deck

1. User clicks "New Deck" button in the header
2. `showCreateModal()` is called: all form fields are cleared, modal title set to "New Deck", precon fields hidden
3. The `#deck-modal` backdrop becomes visible (receives `.active` class)
4. User fills in at minimum the Name field (required)
5. Optionally: user selects a format, adds a description, checks "Preconstructed deck" (which reveals origin set, theme, variation fields), sets sleeve color, deck box, storage location
6. User clicks "Save"
7. `saveDeck()` validates the name is non-empty (alerts if empty), then sends `POST /api/decks` with the form data as JSON
8. On success: the modal closes and `window.location.href` is set to `/decks/{new_id}`, navigating to the new deck's detail page
9. Alternatively, user clicks "Cancel" or clicks the backdrop to close the modal without saving

### Flow 4: Toggle Precon Fields in Create/Edit Modal

1. User checks the "Preconstructed deck" checkbox (`#f-precon`)
2. `togglePreconFields()` is called
3. The `#precon-fields` div becomes visible, revealing: Origin Set dropdown (JMP/J22/J25), Theme text input, Variation number input (1-4)
4. User unchecks the checkbox: the precon fields hide again

### Flow 5: Close Modal via Backdrop Click

1. Any modal is open (`#deck-modal`, `#add-cards-modal`, or `#expected-modal`)
2. User clicks on the dark backdrop area (outside the modal content)
3. The event listener on `.modal-backdrop` detects `e.target === el` (the backdrop itself, not the modal)
4. The `.active` class is removed, closing the modal

---

## 5. Dynamic Behavior

### On Page Load
- `loadDecks()` is called immediately at script end (line 1015)
- Fetches `GET /api/decks` asynchronously
- Renders the deck grid or empty state based on results
- No loading indicator is shown during the fetch

### Deck Grid Rendering
- Each deck is rendered as an `<a>` tag with class `deck-card`, linking to `/decks/{id}`
- The card displays: deck name (`<h3>`), format badge, precon badge (purple), storage location, description, card count, total value (if non-zero)
- All text content is HTML-escaped via the `esc()` function

### Modal System
- Modals use CSS `.modal-backdrop` (initially `display: none`) that becomes `display: flex` when `.active` is added
- Three modals exist: `#deck-modal` (create/edit), `#add-cards-modal` (card picker), `#expected-modal` (expected list)
- Modals can be closed by: Cancel button, backdrop click, or successful form submission
- The Create/Edit modal is shared -- `editingDeckId` determines whether save performs POST (create) or PUT (update)

### Legacy Inline Detail View
- The page has a `#detail-view` div that can be activated via `showDeck(id)` JS function
- This switches visibility between `#list-view` and `#detail-view`
- With the introduction of the standalone `/decks/:id` page, this inline view is no longer the primary path -- deck cards now link directly to the standalone page
- The inline detail view includes: zone tabs, card table with checkboxes, completeness tracking, and all deck CRUD operations

---

## 6. Data Dependencies

### API Endpoints Used

| Method | Endpoint | When Called | Response Shape |
|--------|----------|------------|----------------|
| `GET` | `/api/decks` | Page load (`loadDecks()`), and when returning from detail view (`showList()`) | `[{id, name, description, format, is_precon, sleeve_color, deck_box, storage_location, origin_set_code, origin_theme, origin_variation, created_at, updated_at, card_count, total_value}, ...]` |
| `GET` | `/api/decks/:id` | `showDeck(id)` (legacy inline) | Single deck object (same shape as list item) |
| `GET` | `/api/decks/:id/cards` | `loadDeckCards()` (legacy inline) | `[{id, printing_id, finish, condition, language, purchase_price, acquired_at, deck_zone, set_code, collector_number, rarity, artist, image_uri, name, type_line, mana_cost, cmc, colors, ...}, ...]` |
| `GET` | `/api/decks/:id/expected` | `loadCompleteness()` (legacy inline) | `[{oracle_id, name, qty}, ...]` or `[]` |
| `GET` | `/api/decks/:id/completeness` | `loadCompleteness()` (legacy inline) | `{present: [{name, actual_qty, expected_qty}], missing: [{name, actual_qty, expected_qty, locations: [{collection_id, deck_name, binder_name}]}], extra: [{oracle_id, name, zone, actual_qty}]}` |
| `POST` | `/api/decks` | `saveDeck()` when creating | Returns created deck object |
| `PUT` | `/api/decks/:id` | `saveDeck()` when editing (legacy inline) | Returns updated deck object |
| `DELETE` | `/api/decks/:id` | `deleteDeck()` (legacy inline) | -- |
| `POST` | `/api/decks/:id/cards` | `addSelectedPickerCards()` (legacy inline) | `{collection_ids, zone}` body |
| `DELETE` | `/api/decks/:id/cards` | `removeSelectedCards()` (legacy inline) | `{collection_ids}` body |
| `POST` | `/api/decks/:id/expected` | `importExpectedList()` (legacy inline) | `{decklist}` body |
| `POST` | `/api/decks/:id/reassemble` | `reassembleCard()` / `reassembleAll()` (legacy inline) | `{collection_ids}` body |
| `GET` | `/api/collection?q=...&status=owned` | `searchPickerCards()` (legacy inline) | Collection cards matching search |
| `GET` | `/api/collection/copies?printing_id=...&finish=...` | `addSelectedPickerCards()` (legacy inline) | Individual copies for a printing |

### Required Data
- The page functions with zero decks (shows empty state)
- Deck creation requires no pre-existing data
- The card picker (legacy inline) searches owned cards in the collection -- requires cards to exist in the collection
- Expected list import requires card names to be resolvable against the local database

---

## 7. Visual States

### State 1: Empty -- No Decks Exist
- The `#deck-grid` is empty
- `#empty-state` div is visible with message: "No decks yet. Click 'New Deck' to create one."
- Only the "New Deck" button is available in the header

### State 2: Loaded -- Decks Exist
- `#empty-state` is hidden
- `#deck-grid` shows a responsive grid of deck cards (min 280px wide, auto-fill columns)
- Each card shows: deck name (red/accent), optional format badge (dark blue), optional precon badge (purple), optional storage location, optional description, card count, optional total value
- Cards have hover effect: border color changes to accent, background lightens slightly

### State 3: Create Modal Open
- `#deck-modal` backdrop is visible with dark overlay
- Modal shows "New Deck" title
- All form fields are empty/default
- Precon fields are hidden
- Focus on any input shows accent-colored outline

### State 4: Create Modal with Precon Fields
- Same as State 3 but "Preconstructed deck" checkbox is checked
- Additional fields visible: Origin Set dropdown, Theme text input, Variation number input

### State 5: Validation Error
- If user clicks Save with empty name: browser `alert()` is shown with "Name is required"
- Modal remains open with entered data preserved

### State 6: Network Error / API Failure
- No explicit error handling for the list fetch -- if `/api/decks` fails, the grid may remain empty or show stale data
- No loading spinner is shown during the initial deck list fetch
- The `#status` span exists but is not actively used for error display
