# Edit Order Page UX Description

**Source file:** `mtg_collector/static/edit_order.html`
**URL pattern:** `/edit-order?id=N` (where N is an order ID)

---

## 1. Page Purpose

The Edit Order page allows users to view and modify all details of an existing purchase order, including seller metadata, pricing breakdown, and the individual cards associated with the order. The page is split into two panels: a left sidebar for order metadata (seller, date, source, financial totals) and a right main area for the card list, where users can inline-edit card attributes, add new cards via search, replace cards with different printings, and remove cards. Changes to order metadata are saved explicitly via a button, while card-level edits (condition, finish, price) are saved automatically on change.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "MTG Collection" | Header link (`<a>`) | `/` | Returns to the home/index page. Styled in red (#e94560). |

There is no additional navigation bar, sidebar nav, or breadcrumb. The header contains only the home link and the page title "Edit Order".

---

## 3. Interactive Elements

### Order Metadata Panel (left sidebar, `#meta-panel`)

These elements are rendered dynamically by `renderMeta()` after the order loads.

| Element | ID | Type | Purpose |
|---------|----|------|---------|
| Seller Name | `#meta-seller` | `<input type="text">` | The name of the seller/vendor for this order. Pre-filled from `orderData.seller_name`. |
| Order # | `#meta-order-num` | `<input type="text">` | The order number/reference. Pre-filled from `orderData.order_number`. |
| Date | `#meta-date` | `<input type="date">` | The order date. Pre-filled from `orderData.order_date`. Native date picker. |
| Source | `#meta-source` | `<select>` | The marketplace source. Options: `tcgplayer` ("TCGPlayer"), `cardkingdom` ("Card Kingdom"), `other` ("Other"). Pre-selected from `orderData.source`. |
| Notes | `#meta-notes` | `<textarea rows="3">` | Free-text notes about the order. Vertically resizable. Pre-filled from `orderData.notes`. |
| Subtotal | `#meta-subtotal` | `<input type="number" step="0.01">` | Order subtotal in dollars. Pre-filled from `orderData.subtotal`. |
| Shipping | `#meta-shipping` | `<input type="number" step="0.01">` | Shipping cost in dollars. Pre-filled from `orderData.shipping`. |
| Tax | `#meta-tax` | `<input type="number" step="0.01">` | Tax amount in dollars. Pre-filled from `orderData.tax`. |
| Total | `#meta-total` | `<input type="number" step="0.01">` | Order total in dollars. Pre-filled from `orderData.total`. |
| Save Order Details | `#save-meta-btn` | `<button class="btn-primary">` | Saves all metadata fields via PUT request. Disables while saving, shows "Saving..." text. |
| Save Status | `#meta-save-status` | `<div>` | Container for success/error messages after save. Auto-clears success after 2 seconds. |

### Cards Panel (right main area, `#cards-panel`)

These elements are rendered dynamically by `renderCards()` after the order loads.

| Element | ID / Selector | Type | Purpose |
|---------|--------------|------|---------|
| Add Card | `#add-card-btn` | `<button class="btn-secondary">` | Opens the search overlay in "add" mode. Label is "+ Add Card". |
| Condition (per card) | `select[data-field="condition"][data-id="N"]` | `<select>` | Card condition. Options: "Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged". Saves on change. |
| Finish (per card) | `select[data-field="finish"][data-id="N"]` | `<select>` | Card finish type. Options: "nonfoil", "foil", "etched". Saves on change. |
| Price (per card) | `input[data-field="purchase_price"][data-id="N"]` | `<input type="number" step="0.01">` | Purchase price for this card. Placeholder text is "Price". Width: 70px. Saves on change. |
| Replace Card (per card) | `<button class="btn-icon" title="Replace card">` | `<button>` | Icon button showing arrows (&#x21C4;). Opens search overlay in "replace" mode for this card. Uses inline `onclick="openSearch('replace', cardId)"`. |
| Remove Card (per card) | `<button class="btn-icon danger" title="Remove card">` | `<button>` | Icon button showing X (&#x2715;). Prompts confirm dialog, then deletes card from collection. Uses inline `onclick="removeCard(cardId)"`. |

### Search Overlay (`#search-overlay`)

| Element | ID | Type | Purpose |
|---------|----|------|---------|
| Search Input | `#search-input` | `<input type="text">` | Text input for card name search. Placeholder: "Search for a card...". Autocomplete off. Debounced at 300ms, minimum 2 characters. Auto-focused when overlay opens. |
| Close Button | `#search-close` | `<button>` | Displays "x" character. Closes the search overlay. |
| Search Results | `#search-results` | `<div>` | Container for search result cards. Displays a grid of clickable card candidates. |
| Search Candidate (per result) | `.search-candidate[data-printing-id="X"]` | `<div>` | Clickable card tile with image, name, and set info. Clicking selects the candidate for add or replace action. |

---

## 4. User Flows

### Flow 1: Load and View an Order

1. User navigates to `/edit-order?id=N` where N is a valid order ID.
2. Page displays loading spinners in both panels ("Loading order..." and "Loading cards...").
3. JavaScript reads `id` from the query string and fetches order metadata and cards in parallel.
4. Left panel renders the order metadata form pre-filled with existing data.
5. Right panel renders the summary bar (card count, total value) and the card list.

### Flow 2: Edit Order Metadata

1. User modifies any combination of: seller name, order number, date, source, notes, subtotal, shipping, tax, total.
2. User clicks "Save Order Details" button.
3. Button text changes to "Saving..." and becomes disabled.
4. A PUT request is sent to `/api/orders/{orderId}` with all metadata fields.
5. On success: a green "Saved" message appears below the button and auto-disappears after 2 seconds.
6. On failure: a red error message appears below the button with the error text.
7. Button re-enables and text reverts to "Save Order Details".

### Flow 3: Inline Edit a Card's Condition, Finish, or Price

1. User changes the condition dropdown, finish dropdown, or price input on any card row.
2. On the `change` event, a PUT request is sent to `/api/collection/{cardId}` with the changed field.
3. No visual feedback is shown to the user (fire-and-forget; errors logged to console only).

### Flow 4: Add a New Card to the Order

1. User clicks "+ Add Card" button in the summary bar.
2. Search overlay appears with empty search input auto-focused.
3. User types at least 2 characters of a card name.
4. After 300ms debounce, a POST request is sent to `/api/ingest2/search-card` with the query.
5. Results appear as a grid of card images with names and set info.
6. User clicks a card candidate.
7. Overlay closes. A POST request is sent to `/api/orders/{orderId}/add-card` with the selected `printing_id`.
8. The card list refreshes, showing the newly added card. Summary bar updates with new count and total.

### Flow 5: Replace a Card in the Order

1. User clicks the replace button (arrows icon) on a card row.
2. Search overlay appears with empty search input auto-focused.
3. User searches for and selects a replacement card (same search flow as adding).
4. Overlay closes. A PUT request is sent to `/api/collection/{cardId}` with the new `printing_id`.
5. The card list refreshes, showing the replaced card.

### Flow 6: Remove a Card from the Order

1. User clicks the remove button (X icon) on a card row.
2. A browser `confirm()` dialog appears: "Remove this card from the order?"
3. If user cancels, nothing happens.
4. If user confirms, a DELETE request is sent to `/api/collection/{cardId}?confirm=true`.
5. The card list refreshes without the removed card. Summary bar updates with new count and total.

### Flow 7: Close Search Without Selecting

1. User opens the search overlay via "Add Card" or "Replace Card".
2. User clicks the close button (X) in the search modal header, OR clicks the dark backdrop outside the modal.
3. Overlay closes. No changes are made.

### Flow 8: Access Page Without Order ID

1. User navigates to `/edit-order` (no `?id=` parameter).
2. Left panel shows error: "No order ID specified. Use ?id=N".
3. Right panel is empty. No API calls are made.

---

## 5. Dynamic Behavior

### On Page Load

- The `id` query parameter is read from the URL. If missing, an error is shown immediately and no further loading occurs.
- If present, `loadOrder()` is called, which fires two parallel `fetch` requests:
  - `GET /api/orders/{orderId}` for order metadata
  - `GET /api/orders/{orderId}/cards` for the card list
- Both panels show animated spinner loading indicators until data arrives.
- Once both responses resolve, `renderMeta()` and `renderCards()` populate the DOM.

### Search Overlay

- Hidden by default (`display: none`). Toggled via the `.active` CSS class.
- Uses a fixed-position full-screen overlay with semi-transparent black backdrop.
- The search input is debounced at 300ms (`setTimeout` with `clearTimeout`).
- Minimum query length is 2 characters before a search is triggered.
- While searching, a spinner and "Searching..." text are shown.
- Results are displayed in a responsive CSS Grid (auto-fill columns, min 130px each).
- Each result card shows: image (lazy loaded), card name (truncated), set code + collector number.
- Clicking anywhere on the backdrop (outside the modal) closes the overlay.

### Inline Card Updates

- Condition and finish dropdowns, plus the price input, fire on `change` event.
- Updates are sent immediately via PUT to `/api/collection/{cardId}` with the single changed field.
- No loading indicator or success feedback is shown for inline edits.
- Errors are silently logged to console.

### Card List Refresh

- After add, replace, or remove operations, `refreshCards()` re-fetches the full card list from `/api/orders/{orderId}/cards` and re-renders the entire cards panel.
- The summary bar (card count and total value) is recalculated on each render from the `orderCards` array.

### Save Button State

- The "Save Order Details" button is disabled and shows "Saving..." during the save request.
- Re-enabled and text restored after the request completes (success or failure).
- Success message auto-clears after 2 seconds via `setTimeout`.

### Card Images

- Card thumbnails in the list use the `/small/` Scryfall image variant (the image URI is rewritten from `/normal/` to `/small/`).
- If no image URI is available, a solid dark blue placeholder div is shown.
- All images use `loading="lazy"` for deferred loading.
- Search result images use the full image URI as-is (not resized).

---

## 6. Data Dependencies

### API Endpoints Used

| Method | Endpoint | When Called | Request Body | Response |
|--------|----------|-------------|-------------|----------|
| `GET` | `/api/orders/{orderId}` | Page load | -- | Order metadata JSON (seller_name, order_number, order_date, source, notes, subtotal, shipping, tax, total) |
| `GET` | `/api/orders/{orderId}/cards` | Page load + after any card mutation | -- | Array of card objects (id, name, set_code, collector_number, image_uri, condition, finish, purchase_price) |
| `PUT` | `/api/orders/{orderId}` | Save metadata button click | `{ seller_name, order_number, order_date, source, notes, subtotal, shipping, tax, total }` | Success/error status |
| `PUT` | `/api/collection/{cardId}` | Inline condition/finish/price change | `{ [field]: value }` | Success/error status |
| `PUT` | `/api/collection/{cardId}` | Replace card (from search) | `{ printing_id: "..." }` | Success/error status |
| `DELETE` | `/api/collection/{cardId}?confirm=true` | Remove card (after confirm) | -- | Success/error status |
| `POST` | `/api/ingest2/search-card` | Search overlay typing (debounced) | `{ query: "..." }` | `{ candidates: [{ printing_id, name, image_uri, set_code, collector_number }] }` |
| `POST` | `/api/orders/{orderId}/add-card` | Select candidate in "add" mode | `{ printing_id: "..." }` | Success/error status |

### Prerequisites

- An order must exist in the database with the given ID.
- The order must have associated cards in the `collection` table (linked via `order_id`) for the card list to be populated.
- The `/api/ingest2/search-card` endpoint must have access to the local card database (populated via `mtg cache all`) for search to return results.

---

## 7. Visual States

### State 1: Loading

- Both panels show a blue info-styled message with an animated spinner.
- Left panel: "Loading order..." with spinner.
- Right panel: "Loading cards..." with spinner.
- This is the initial state while the two parallel API calls are in flight.

### State 2: No Order ID (Error)

- Left panel shows a red error message: "No order ID specified. Use ?id=N".
- Right panel is completely empty (innerHTML cleared).
- No API calls are made.

### State 3: Order Not Found (Error)

- Left panel shows a red error message: "Order not found".
- Right panel is completely empty (innerHTML cleared).
- Occurs when the GET `/api/orders/{orderId}` returns a non-OK status.

### State 4: Order Loaded with Cards

- Left panel shows the fully populated metadata form (all fields filled with order data).
- Right panel shows:
  - Summary bar with card count (e.g., "5 cards") and total value (e.g., "Total value: $12.50").
  - "+ Add Card" button in the summary bar.
  - A vertical list of card rows, each with: thumbnail, name, set/number, condition dropdown, finish dropdown, price input, replace button, remove button.

### State 5: Order Loaded with No Cards

- Left panel shows the populated metadata form.
- Right panel shows:
  - Summary bar with "0 cards" and "Total value: $0.00".
  - "+ Add Card" button.
  - Empty card list (no card rows).

### State 6: Save In Progress

- "Save Order Details" button shows "Saving..." text and is visually dimmed (opacity 0.5, cursor not-allowed).
- All form fields remain editable during save.

### State 7: Save Success

- Button reverts to "Save Order Details" and re-enables.
- A green success message "Saved" appears in `#meta-save-status` below the button.
- The success message auto-disappears after 2 seconds.

### State 8: Save Error

- Button reverts to "Save Order Details" and re-enables.
- A red error message appears in `#meta-save-status` with the error text (e.g., "Failed to save").
- The error message persists until the next save attempt.

### State 9: Search Overlay Open (Empty)

- Full-screen dark backdrop covers the page.
- Centered modal (700px wide, max 90vw, max 80vh) with:
  - Search input (focused, empty) with placeholder "Search for a card...".
  - Close button (X) in the header.
  - Message in results area: "Type a card name to search".

### State 10: Search Overlay (Searching)

- Search input contains the user's query.
- Results area shows a spinner and "Searching..." text.

### State 11: Search Overlay (Results Found)

- Results area shows a responsive grid of card candidates.
- Each candidate shows: card image, name (truncated), set code + collector number.
- Cards have a hover state with a red border highlight.

### State 12: Search Overlay (No Results)

- Results area shows: "No results found" in gray text, centered.

### State 13: Search Overlay (Error)

- Results area shows a red error message: "Search failed: {error message}".

### State 14: Remove Confirmation Dialog

- A native browser `confirm()` dialog appears over the page: "Remove this card from the order?"
- Two options: OK (proceeds with deletion) or Cancel (dismisses, no action).

### Responsive Layout (Mobile, <= 768px)

- The two-panel layout stacks vertically (metadata panel on top, cards panel below).
- Metadata panel takes full width with a bottom border instead of a right border.
- Card rows wrap their controls to a new line, right-aligned.
