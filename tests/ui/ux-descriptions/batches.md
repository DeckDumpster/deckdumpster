# Batches Page UX Description

**URL:** `/batches`
**Source:** `mtg_collector/static/batches.html`
**Title:** Batches - MTG Collection

---

## 1. Page Purpose

The Batches page provides a unified view of all card ingestion batches in the collection. A "batch" represents a group of cards that were imported together through any ingestion method (corner photo recognition, OCR, CSV import, manual ID entry, or order import). Users can browse all batches, filter them by ingestion type, drill into a specific batch to see its cards, and assign an entire batch to a deck. This page serves as the audit trail and management interface for how cards entered the collection.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "Batches" | `<h1>` | N/A (current page title) | Header, leftmost |
| "Home" | `<a href="/">` | Home page | Header |
| "Collection" | `<a href="/collection">` | Collection page | Header |

---

## 3. Interactive Elements

### List View (default view)

| Element | ID / Selector | Type | Description |
|---------|--------------|------|-------------|
| Filter pill: All | `#type-filter .pill[data-type=""]` | `<span>` (clickable) | Shows all batches regardless of type. Active by default (has `.active` class). |
| Filter pill: Corner | `#type-filter .pill[data-type="corner"]` | `<span>` (clickable) | Filters to show only corner-identified batches. |
| Filter pill: OCR | `#type-filter .pill[data-type="ocr"]` | `<span>` (clickable) | Filters to show only OCR-identified batches. |
| Filter pill: CSV Import | `#type-filter .pill[data-type="csv_import"]` | `<span>` (clickable) | Filters to show only CSV-imported batches. |
| Filter pill: Manual ID | `#type-filter .pill[data-type="manual_id"]` | `<span>` (clickable) | Filters to show only manual ID entry batches. |
| Filter pill: Orders | `#type-filter .pill[data-type="order"]` | `<span>` (clickable) | Filters to show only order-imported batches. |
| Batch cards | `.batch-card` (multiple) | `<div>` (clickable) | Each card in the grid. Clicking invokes `showBatch(batchId)` to drill into that batch. |

### Detail View (shown when a batch is selected)

| Element | ID / Selector | Type | Description |
|---------|--------------|------|-------------|
| Back button | `.detail-header button.secondary` | `<button>` | Returns to the list view. Calls `backToList()`. |
| Deck assignment dropdown | `#assign-deck-select` | `<select>` | Dropdown populated with all decks. Only shown if the batch is not already assigned to a deck. First option is "Select a deck..." (value=""). |
| Zone assignment dropdown | `#assign-zone-select` | `<select>` | Dropdown with three options: Mainboard (default), Sideboard, Commander. Only shown if the batch is not already assigned to a deck. |
| Assign button | `.assign-row button` | `<button>` | Assigns the entire batch to the selected deck and zone. Calls `assignDeck()`. Only shown if batch is not already assigned. |

### Containers / Display Areas

| Element | ID | Description |
|---------|-----|-------------|
| List view container | `#list-view` | Holds the batch grid. Visible by default. |
| Detail view container | `#detail-view` | Holds the batch detail. Hidden by default (`display: none`). |
| Messages container | `#messages` | Global messages area (not actively used in current code). |
| Detail messages | `#detail-messages` | Shows success/error messages within the detail view. Dynamically created during `renderDetail()`. |

---

## 4. User Flows

### Flow 1: Browse All Batches

1. User navigates to `/batches`.
2. Page loads and immediately calls `loadBatches()`, which fetches `GET /api/batches`.
3. The batch grid renders in `#list-view` with one card per batch.
4. Each batch card displays: batch name (or "Batch #ID"), type badge (color-coded), creation date, card count, optional metadata (product type, set code, order number, seller name), and optional deck assignment.

### Flow 2: Filter Batches by Type

1. User clicks one of the filter pills in the `#type-filter` bar (Corner, OCR, CSV Import, Manual ID, Orders).
2. The clicked pill gets `.active` class; all others lose it.
3. `loadBatches()` is called with `GET /api/batches?type=<filter_value>`.
4. The batch grid re-renders showing only batches of the selected type.
5. Clicking "All" clears the filter and shows all batches.

### Flow 3: View Batch Details

1. User clicks a batch card in the grid.
2. `showBatch(batchId)` fetches `GET /api/batches/{batchId}/cards` to get batch metadata and cards.
3. `GET /api/decks` is also fetched to populate the deck assignment dropdown.
4. The list view is hidden and the detail view is shown.
5. Detail view displays: batch name, creation date, card count, type (color-coded), product type, set code, notes, order info.
6. A card grid shows all cards in the batch with images (from `image_uri` or fallback `/static/card_back.jpeg`), card name, set code, and collector number.

### Flow 4: Assign Batch to Deck (unassigned batch)

1. User views a batch detail that is not yet assigned to a deck.
2. The assign section shows a deck dropdown, a zone dropdown, and an "Assign" button.
3. User selects a deck from the dropdown.
4. User optionally changes the zone (defaults to Mainboard).
5. User clicks "Assign".
6. `POST /api/batches/{batchId}/assign-deck` is called with `{ deck_id, deck_zone }`.
7. On success: a green success message appears showing the number of cards assigned. The detail view re-renders showing "Assigned to: DeckName (zone)" instead of the dropdowns. The list view is also refreshed via `loadBatches()`.
8. On error: a red error message appears and auto-dismisses after 10 seconds.

### Flow 5: View Already-Assigned Batch

1. User views a batch detail that is already assigned to a deck.
2. Instead of the dropdown/assign controls, a green status message shows "Assigned to: DeckName (zone)".
3. No further assignment actions are available.

### Flow 6: Return to List from Detail

1. User clicks the "Back" button in the detail view header.
2. The detail view is hidden (`display: none`) and the list view is shown (`display: block`).
3. The list view retains its previous state (including any active filter).

---

## 5. Dynamic Behavior

### On Page Load
- `loadBatches()` is called immediately, fetching all batches from `GET /api/batches`.
- The batch grid is rendered client-side from the JSON response.

### Filter Interaction
- Clicking a filter pill triggers a new API call with the `type` query parameter.
- The active pill styling updates immediately (CSS class toggle).
- The entire batch grid is re-rendered from the new response.

### Batch Detail Loading
- Clicking a batch card triggers two sequential API calls: batch cards, then decks.
- The list view and detail view swap visibility (no page navigation, purely JS state).

### Deck Assignment
- After successful assignment, both the detail view and the list view are refreshed.
- Success/error messages appear as dynamically created `<div>` elements in `#detail-messages`.
- Messages auto-dismiss after 10 seconds via `setTimeout`.

### Card Images
- Images use `loading="lazy"` for deferred loading.
- Fallback image is `/static/card_back.jpeg` when `image_uri` is null.

### Type Color Coding
- Each batch type has a distinct color: corner (#e94560 red), ocr (#88c0d0 light blue), csv_import (#a3be8c green), manual_id (#d08770 orange), order (#b48ead purple).
- The type badge uses the color for text and a 20% opacity version for background.

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request | Response |
|----------|--------|------|---------|----------|
| `/api/batches` | GET | Page load, filter change | Optional query: `?type=corner\|ocr\|csv_import\|manual_id\|order` | Array of batch objects with `id`, `name`, `batch_type`, `created_at`, `card_count`, `deck_name`, `deck_id`, `deck_zone`, `product_type`, `set_code`, `order_number`, `seller_name`, `notes` |
| `/api/batches/{id}/cards` | GET | Clicking a batch card | N/A | `{ batch: {...}, cards: [...] }` where cards have `name`, `image_uri`, `set_code`, `collector_number` |
| `/api/decks` | GET | Opening batch detail | N/A | Array of deck objects with `id`, `name`, `format` |
| `/api/batches/{id}/assign-deck` | POST | Clicking "Assign" | `{ deck_id: int, deck_zone: string }` | `{ assigned: int }` on success, `{ error: string }` on failure |

### Data Prerequisites
- Batches must exist in the database (created by CSV import, corner identification, OCR, manual ID entry, or order import).
- Decks must exist for the assignment feature to be useful.
- Cards in batches must have `image_uri` populated for card images to display.

---

## 7. Visual States

### List View States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Empty (no batches)** | `batches.length === 0` | Centered gray text: "No batches yet. Import cards via CSV, corners, or orders to create batches." inside `.empty-state`. |
| **Populated** | `batches.length > 0` | Responsive grid of batch cards (min 300px per card, auto-fill columns). Each card has name, type badge, date, card count, and optional metadata. |
| **Filtered empty** | Filter active but no matching batches | Same empty state message. |
| **Filtered populated** | Filter active with matching batches | Grid shows only batches matching the selected type filter. |

### Detail View States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Unassigned batch** | `batch.deck_id` is falsy | Shows deck dropdown, zone dropdown, and "Assign" button in the assign section. |
| **Assigned batch** | `batch.deck_id` is truthy | Shows green "Assigned to: DeckName (zone)" text. No dropdowns or assign button. |
| **Assignment success** | After successful `assignDeck()` | Green success message: "Assigned N card(s) to deck". Auto-dismisses after 10 seconds. Detail re-renders to show assigned state. |
| **Assignment error** | API returns error or network failure | Red error message with error text. Auto-dismisses after 10 seconds. |
| **Cards with images** | Cards have `image_uri` | Card grid shows card art images with 5:7 aspect ratio. |
| **Cards without images** | Cards lack `image_uri` | Card grid shows fallback card back image (`/static/card_back.jpeg`). |

### Responsive States

| Breakpoint | Behavior |
|------------|----------|
| Desktop (> 768px) | Batch grid uses multi-column layout (min 300px). Card grid uses multi-column (min 140px). |
| Mobile (<= 768px) | Batch grid collapses to single column. Card grid uses smaller columns (min 100px). |
