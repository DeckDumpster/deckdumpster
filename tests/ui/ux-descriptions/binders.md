# Binders Page UX Description

**Source file:** `mtg_collector/static/binders.html`
**URL:** `/binders`

---

## 1. Page Purpose

The Binders page allows users to manage physical binder groupings for their MTG card collection. Users can create, view, edit, and delete binders -- each representing a real-world binder with metadata like color, type (9-pocket, 4-pocket, side-loading), and storage location. From the binder detail view, users can add cards from their collection into a binder, view the cards currently assigned, and remove cards. A card can only be in one binder or one deck at a time (mutually exclusive). The page operates in two modes: a list view showing all binders as a card grid, and a detail view showing a single binder's metadata and card contents.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "MTG" link in header | `<a href="/">` | Homepage (`/`) | Part of the breadcrumb `MTG / Binders` |
| "Back to Binders" button | `<button class="secondary">` | Returns to list view | Only visible in detail view; calls `showList()`, does not navigate to a new URL |

The page has no sidebar, no tab bar, and no other outbound navigation links. All transitions between list view and detail view happen client-side without URL changes.

---

## 3. Interactive Elements

### Header Controls (List View) -- `#list-controls`

| Element | ID / Selector | Type | Action |
|---------|---------------|------|--------|
| "New Binder" button | (no ID) button in `#list-controls` | `<button>` | Opens the Create/Edit modal in "create" mode via `showCreateModal()` |

### Header Controls (Detail View) -- `#detail-controls`

| Element | ID / Selector | Type | Action |
|---------|---------------|------|--------|
| "Back to Binders" button | (no ID) button.secondary in `#detail-controls` | `<button class="secondary">` | Returns to list view via `showList()` |
| "Add Cards" button | (no ID) button in `#detail-controls` | `<button>` | Opens the Add Cards modal via `showAddCardsModal()` |
| "Remove Selected" button | (no ID) button.secondary in `#detail-controls` | `<button class="secondary">` | Removes checked cards from the binder via `removeSelectedCards()` |

### Status Indicator

| Element | ID | Type | Notes |
|---------|-----|------|-------|
| Status text | `#status` | `<span>` | Right-aligned in header; not currently written to by any JS function (reserved for future use) |

### Detail View Actions

| Element | ID / Selector | Type | Action |
|---------|---------------|------|--------|
| "Edit" button | (no ID) button.secondary in `.actions` | `<button class="secondary">` | Opens the Create/Edit modal in "edit" mode via `showEditModal()` |
| "Delete Binder" button | (no ID) button.danger in `.actions` | `<button class="danger">` | Deletes the binder after a `confirm()` dialog via `deleteBinder()` |

### Card Table

| Element | ID / Selector | Type | Action |
|---------|---------------|------|--------|
| Select-all checkbox | `#select-all` | `<input type="checkbox">` | Toggles selection of all cards in the table via `toggleSelectAll(this)` |
| Per-card checkbox | `[data-id]` checkbox in each row | `<input type="checkbox">` | Toggles selection of individual card via `toggleCardSelect(id, checked)` |

Table columns: Checkbox, Name, Set (code + collector number), Mana, Type, Finish, Condition.

### Create/Edit Binder Modal -- `#binder-modal`

| Element | ID | Type | Placeholder / Options | Required |
|---------|-----|------|-----------------------|----------|
| Modal title | `#modal-title` | `<h3>` | "New Binder" or "Edit Binder" | N/A |
| Name input | `#f-name` | `<input type="text">` | "My Trade Binder" | Yes (validated in JS) |
| Description textarea | `#f-description` | `<textarea rows="2">` | (none) | No |
| Color input | `#f-color` | `<input type="text">` | "e.g. blue, black ultra pro" | No |
| Binder Type dropdown | `#f-type` | `<select>` | `-- None --`, `9-Pocket`, `4-Pocket`, `Side-Loading` | No |
| Storage Location input | `#f-location` | `<input type="text">` | "e.g. bookshelf, top row" | No |
| "Save" button | (no ID) button in `.form-actions` | `<button>` | Calls `saveBinder()` -- POST (create) or PUT (edit) | N/A |
| "Cancel" button | (no ID) button.secondary in `.form-actions` | `<button class="secondary">` | Calls `closeModal('binder-modal')` | N/A |

### Add Cards Modal -- `#add-cards-modal`

| Element | ID | Type | Placeholder | Notes |
|---------|-----|------|-------------|-------|
| Search input | `#picker-search` | `<input type="text">` | "Search by name..." | Fires `searchPickerCards()` on every keystroke (`oninput`) |
| Card picker list | `#picker-cards` | `<div class="picker-cards">` | Initial: "Type to search your collection..." | Scrollable list, max-height 300px |
| Individual picker card | `.picker-card` (dynamic) | `<div>` | N/A | Click toggles selection (`.selected` class); shows name, set code, collector number, finish, quantity |
| "Add Selected" button | (no ID) button in `.form-actions` | `<button>` | Calls `addSelectedPickerCards()` | N/A |
| "Cancel" button | (no ID) button.secondary in `.form-actions` | `<button class="secondary">` | Calls `closeModal('add-cards-modal')` | N/A |

### Binder Cards (List View Grid)

| Element | Selector | Type | Action |
|---------|----------|------|--------|
| Binder card | `.binder-card` (dynamic) | `<div>` | Click navigates to detail view via `showBinder(id)` |

Each binder card displays: name (h3), binder type badge, color, storage location, description, card count, and total value.

---

## 4. User Flows

### Flow 1: View All Binders

1. User navigates to `/binders`.
2. Page loads and immediately calls `loadBinders()` which fetches `GET /api/binders`.
3. If binders exist, they render as a responsive card grid (`#binder-grid`).
4. If no binders exist, the empty state message is shown: "No binders yet. Click 'New Binder' to create one."
5. Each binder card shows: name, binder type badge (if set), color (if set), storage location (if set), description (if set), card count, and total value (if non-zero).

### Flow 2: Create a New Binder

1. User clicks "New Binder" button in the header.
2. The Create/Edit modal opens with title "New Binder" and all fields cleared.
3. User fills in the Name field (required) and optionally: Description, Color, Binder Type, Storage Location.
4. User clicks "Save".
5. If name is empty, a browser `alert('Name is required')` fires and the modal stays open.
6. If name is provided, a `POST /api/binders` request is sent with the form data as JSON.
7. The modal closes and the page navigates to the detail view for the newly created binder (via `showBinder(result.id)`).

### Flow 3: View Binder Details

1. User clicks a binder card in the list view.
2. `showBinder(id)` fetches `GET /api/binders/:id` for binder metadata.
3. The list view hides, detail view appears, and header controls switch from list-controls to detail-controls.
4. Binder metadata renders: name (h2), color, type, location, notes, card count, total value.
5. `loadBinderCards()` fetches `GET /api/binders/:id/cards` and renders the card table.
6. If the binder has no cards, the table body shows a single row: "No cards in this binder".

### Flow 4: Edit a Binder

1. From the detail view, user clicks the "Edit" button.
2. The Create/Edit modal opens with title "Edit Binder" and fields pre-populated with current binder data.
3. User modifies any fields and clicks "Save".
4. A `PUT /api/binders/:id` request is sent with updated data.
5. The modal closes and the detail view re-renders with the updated binder metadata.

### Flow 5: Delete a Binder

1. From the detail view, user clicks the "Delete Binder" button.
2. A browser `confirm()` dialog asks: `Delete "<binder name>"? Cards will be unassigned but not deleted.`
3. If confirmed, a `DELETE /api/binders/:id` request is sent.
4. The page returns to the list view via `showList()`, which reloads the binder list.
5. Cards that were in the binder have their `binder_id` set to NULL (server-side) but remain in the collection.

### Flow 6: Add Cards to a Binder

1. From the detail view, user clicks "Add Cards" button in the header.
2. The Add Cards modal opens with a search input and an empty picker list showing "Type to search your collection..."
3. User types a search term (minimum 2 characters).
4. On each keystroke, `searchPickerCards()` fires, calling `GET /api/collection?q=<query>&status=owned`.
5. Matching cards appear in a scrollable list showing: name, set code + collector number, finish, and quantity owned.
6. If fewer than 2 characters are typed, the picker shows "Type at least 2 characters..."
7. If no results match, the picker shows "No matching cards found".
8. User clicks individual cards to toggle their selection (highlighted with `.selected` class).
9. User clicks "Add Selected".
10. For each selected card, the system fetches `GET /api/collection/copies?printing_id=X&finish=Y` to find individual copies.
11. Only unassigned copies (no `deck_id` and no `binder_id`) are collected.
12. If no unassigned copies exist, an `alert('No unassigned copies found')` is shown.
13. If unassigned copies exist, `POST /api/binders/:id/cards` is called with `{ collection_ids: [...] }`.
14. If the server returns an error (e.g., 409 conflict), it is shown via `alert()`.
15. On success, the modal closes, binder metadata refreshes, and the card table reloads.

### Flow 7: Remove Cards from a Binder

1. From the detail view, user checks one or more cards using per-row checkboxes (or the select-all checkbox in the header).
2. User clicks "Remove Selected" button in the header.
3. If no cards are selected, an `alert('No cards selected')` fires.
4. If cards are selected, `DELETE /api/binders/:id/cards` is called with `{ collection_ids: [...] }`.
5. Binder metadata refreshes (re-fetches `GET /api/binders/:id`) and the card table reloads.
6. Removed cards remain in the collection but are no longer assigned to the binder.

### Flow 8: Select/Deselect All Cards

1. From the detail view with cards loaded, user clicks the select-all checkbox (`#select-all`) in the table header.
2. If checked, all card IDs are added to `selectedCardIds`; if unchecked, all are removed.
3. The card table re-renders with checkboxes reflecting the new state.

### Flow 9: Return to List View

1. From the detail view, user clicks "Back to Binders" button.
2. `showList()` switches to the list view, hides detail-controls, shows list-controls.
3. `loadBinders()` is called to refresh the binder list (reflects any changes made).

### Flow 10: Close Modal via Backdrop Click

1. While any modal is open, user clicks the dark backdrop area outside the modal content.
2. The event listener on `.modal-backdrop` detects `e.target === el` (click was on the backdrop itself, not a child).
3. The modal closes by removing the `active` class.

---

## 5. Dynamic Behavior

### On Page Load
- `loadBinders()` is called immediately at the bottom of the `<script>` block.
- Fetches `GET /api/binders` and renders the binder grid or empty state.

### View Switching (Client-Side)
- The page uses CSS class toggling (`.active`) on `#list-view` and `#detail-view` to switch between modes.
- Header controls also toggle: `#list-controls` vs `#detail-controls` (using `style.display`).
- No URL changes occur; browser back button does not navigate between views.

### Modal System
- Two modals exist: `#binder-modal` (Create/Edit) and `#add-cards-modal` (Add Cards).
- Modals open by adding `.active` class to the `.modal-backdrop`, which switches from `display: none` to `display: flex`.
- Modals close via the Cancel button, Save/Add action completion, or clicking the backdrop.
- The Create/Edit modal is shared: `editingBinderId` determines whether a POST (create) or PUT (update) is issued.
- `#modal-title` text changes between "New Binder" and "Edit Binder" accordingly.

### Picker Search (Debounce-Free)
- The card picker search fires on every `oninput` event with no debouncing.
- Requires a minimum of 2 characters before issuing a fetch.
- Results render as clickable divs; toggling selection adds/removes keys from the `pickerSelected` Set.
- Selection keys are `printingId|finish` composite strings.

### Card Selection State
- `selectedCardIds` (Set) tracks selected card IDs in the detail view table.
- `pickerSelected` (Set) tracks selected cards in the Add Cards picker.
- Both are managed in-memory; state is lost on view transitions.

### Data Refresh After Mutations
- After creating a binder: navigates to detail view of the new binder.
- After editing a binder: re-renders detail metadata in place (no reload).
- After deleting a binder: returns to list view, reloads binder list.
- After adding cards: refreshes binder metadata (re-fetches `GET /api/binders/:id`) and reloads card list.
- After removing cards: refreshes binder metadata and reloads card list.
- Returning to list view always reloads binders via `loadBinders()`.

### HTML Escaping
- All user-supplied data is escaped via the `esc()` helper (creates a text node and reads `innerHTML`).

---

## 6. Data Dependencies

### API Endpoints Used

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|-------------|----------|
| `GET` | `/api/binders` | List all binders | -- | `[{id, name, description, color, binder_type, storage_location, created_at, updated_at, card_count, total_value}, ...]` |
| `GET` | `/api/binders/:id` | Get single binder | -- | `{id, name, description, color, binder_type, storage_location, created_at, updated_at, card_count, total_value}` |
| `POST` | `/api/binders` | Create binder | `{name, description?, color?, binder_type?, storage_location?}` | `{id, name, ...}` (201) |
| `PUT` | `/api/binders/:id` | Update binder | `{name?, description?, color?, binder_type?, storage_location?}` | `{id, name, ...}` |
| `DELETE` | `/api/binders/:id` | Delete binder | -- | `{ok: true}` |
| `GET` | `/api/binders/:id/cards` | List cards in binder | -- | `[{id, printing_id, finish, condition, language, purchase_price, acquired_at, set_code, collector_number, rarity, artist, image_uri, name, type_line, mana_cost, cmc, colors, color_identity, oracle_id, set_name}, ...]` |
| `POST` | `/api/binders/:id/cards` | Add cards to binder | `{collection_ids: [int, ...]}` | `{ok: true, count: N}` or `{error: "..."}` (409) |
| `DELETE` | `/api/binders/:id/cards` | Remove cards from binder | `{collection_ids: [int, ...]}` | `{ok: true, count: N}` |
| `GET` | `/api/collection?q=X&status=owned` | Search collection for picker | -- | `[{name, printing_id, finish, set_code, collector_number, qty}, ...]` or `{cards: [...]}` |
| `GET` | `/api/collection/copies?printing_id=X&finish=Y` | Get individual copies | -- | `[{id, deck_id, binder_id, ...}, ...]` |

### Data Requirements
- The binders table must exist in the database (schema migration).
- For the "Add Cards" flow to work, the user must have cards in their collection with `status=owned` and no existing deck/binder assignment.
- Card data (printings, cards, sets tables) must be populated via `mtg cache all` for the card details to display correctly.

---

## 7. Visual States

### List View States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Empty** | `binders.length === 0` | `#binder-grid` is empty; `#empty-state` div visible with message: "No binders yet. Click 'New Binder' to create one." |
| **Populated** | `binders.length > 0` | Responsive grid of binder cards. Each card shows name, optional badge/color/location/description, card count, and optional total value. |

### Detail View States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Binder with cards** | `binderCards.length > 0` | Metadata header (name, color, type, location, notes, card count, value) + full card table with checkboxes. |
| **Binder with no cards** | `binderCards.length === 0` | Metadata header + table with single row: "No cards in this binder" (centered, gray text). |

### Modal States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Create modal** | `editingBinderId === null` | Title: "New Binder". All fields empty. |
| **Edit modal** | `editingBinderId !== null` | Title: "Edit Binder". Fields pre-populated with current binder data. |
| **Add Cards modal -- initial** | Modal just opened | Search input empty. Picker shows: "Type to search your collection..." |
| **Add Cards modal -- short query** | Search input has < 2 characters | Picker shows: "Type at least 2 characters..." |
| **Add Cards modal -- no results** | Search returns empty | Picker shows: "No matching cards found" |
| **Add Cards modal -- results** | Search returns cards | Scrollable list of picker cards with name, set info, finish, quantity. Selected items highlighted. |
| **Add Cards modal -- card selected** | User clicked a picker card | Card row gets `.selected` class (background highlight). Multiple cards can be selected. |

### Error/Alert States

| Trigger | Type | Message |
|---------|------|---------|
| Save binder with empty name | `alert()` | "Name is required" |
| Remove Selected with no checkboxes | `alert()` | "No cards selected" |
| Add Selected with no picker cards selected | `alert()` | "No cards selected" |
| All copies of selected cards already assigned | `alert()` | "No unassigned copies found" |
| Server returns error on add cards (409 conflict) | `alert()` | Server error message (e.g., "Cards already assigned to a deck or binder: [ids]") |
| Delete binder | `confirm()` | `Delete "<name>"? Cards will be unassigned but not deleted.` |

### Header Control Visibility

| View | `#list-controls` | `#detail-controls` |
|------|-------------------|--------------------|
| List view | Visible (shows "New Binder") | Hidden (`display:none`) |
| Detail view | Hidden (`display:none`) | Visible (shows "Back to Binders", "Add Cards", "Remove Selected") |
