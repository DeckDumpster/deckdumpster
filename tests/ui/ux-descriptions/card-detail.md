# Card Detail Page — UX Description

URL pattern: `/card/:set_code/:collector_number` (e.g., `/card/fdn/100`)

---

## 1. Page Purpose

The Card Detail page provides a full-screen, two-column view of a single Magic: The Gathering card printing. It displays the card image (with flip animation for double-faced cards), metadata (name, type, mana cost, set, rarity, artist, treatments), external market links with prices, wishlist management, a form to add the card to the user's collection, a list of all owned copies with inline controls for disposition/assignment/history, and a price history chart. This is the canonical detail view for any card in the system, linked from the collection modal's "Full page" badge.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "DeckDumpster" (site title) | `<a>` in `<h1>` | `/` | Site header, styled as plain text link |
| "Collection" | `<a>` in `.site-header` | `/collection` | Top nav link |
| "Decks" | `<a>` in `.site-header` | `/decks` | Top nav link |
| "Binders" | `<a>` in `.site-header` | `/binders` | Top nav link |
| "Sealed" | `<a>` in `.site-header` | `/sealed` | Top nav link |
| "SF" badge | `<a>` with class `badge link` | `https://scryfall.com/card/:set/:cn` | Opens in new tab (`target="_blank"`) |
| "CK" badge | `<a>` with class `badge link` | Card Kingdom URL (via `getCkUrl()`) | Opens in new tab (`target="_blank"`) |

---

## 3. Interactive Elements

### Card Image Section

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Flip button | `#flip-btn` | `<button>` | Circular button (bottom-right of image). Toggles a CSS 3D flip animation on the card image. For DFC layouts, also switches the details panel to show the back face's name/type/mana. Displays a clockwise arrow character. |

### Action Buttons (Details Panel)

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Want button | `#want-btn` | `<button>` with class `want-btn` | Toggle: adds/removes the card from the wishlist. Text toggles between "Want" and "Wanted". Gains class `wanted` (green styling) when active. |
| Add button | `#add-btn` | `<button>` with class `add-collection-btn` | Toggle: clicking opens the add-to-collection inline form below; clicking again closes it. |

### Add-to-Collection Form (appears inside `#add-form-container`)

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Date input | `#add-date` | `<input type="date">` | Pre-populated with today's date. Sets `acquired_at` on the new collection entry. |
| Price input | `#add-price` | `<input type="number">` | Optional. `step="0.01"`, `min="0"`. Placeholder: "Price". Sets `purchase_price`. |
| Source input | `#add-source` | `<input type="text">` | Optional. Placeholder: "Source". Sets `source` field. |
| Confirm button | `#add-confirm-btn` | `<button>` | Submits the form. Changes text to "Adding..." and disables while in flight. On success, closes the form and reloads copies. On failure, shows an alert. |

### Price History Chart

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| 1M pill | `.price-range-pill[data-range="30"]` | `<button>` | Filters chart to last 30 days. Active by default (if data spans >= 30 days). |
| 3M pill | `.price-range-pill[data-range="90"]` | `<button>` | Filters chart to last 90 days. |
| 6M pill | `.price-range-pill[data-range="180"]` | `<button>` | Filters chart to last 180 days. |
| 1Y pill | `.price-range-pill[data-range="365"]` | `<button>` | Filters chart to last 365 days. |
| ALL pill | `.price-range-pill[data-range="0"]` | `<button>` | Shows all available price history. |
| Chart canvas | `#price-chart-canvas` | `<canvas>` | Chart.js line chart. Interactive tooltip on hover shows date and price. Vertical crosshair line on hover. Dashed green horizontal lines mark purchase prices of owned copies. |

### Per-Copy Controls (inside `.copy-section[data-copy-id]`)

Each owned copy renders its own set of controls. These are generated dynamically, so they use class selectors rather than IDs.

| Element | Selector | Type | Description |
|---------|----------|------|-------------|
| Receive button | `.receive-btn` | `<button>` | Only shown for copies with `status === 'ordered'`. Marks the copy as received. `data-collection-id` attribute. |
| Dispose dropdown | `.dispose-select` | `<select>` | Options: "Dispose..." (placeholder), "Sold", "Traded", "Gifted", "Lost", "Listed" (if owned), "Unlist" (if listed). |
| Dispose price | `.dispose-price` | `<input type="number">` | Optional sale price for disposition. `step="0.01"`. |
| Dispose note | `.dispose-note` | `<input type="text">` | Optional note for disposition. |
| Dispose button | `.dispose-btn` | `<button>` | Submits the disposition. `data-id` attribute with copy ID. |
| Delete button | `.delete-copy-btn` | `<button>` | Only shown for copies with status `owned` or `ordered`. Prompts browser `confirm()` dialog. `data-id` attribute. |
| Reprocess button | `.reprocess-btn` | `<button>` | Only shown for copies with image lineage. Re-identifies the card from its source image. Prompts confirm. `data-image-id` and `data-image-md5` attributes. |
| Refinish button | `.refinish-btn` | `<button>` | Only shown for copies with image lineage. Removes the card so the user can fix the finish. Prompts confirm. `data-image-id` and `data-image-md5` attributes. |
| Add to Deck dropdown | `.copy-add-to-deck` | `<select>` | Shown for unassigned active copies. Lists all decks plus "New Deck..." option. `data-copy-id` attribute. Selecting "New Deck..." prompts for a name. |
| Add to Binder dropdown | `.copy-add-to-binder` | `<select>` | Shown for unassigned active copies. Lists all binders plus "New Binder..." option. `data-copy-id` attribute. Selecting "New Binder..." prompts for a name. |
| Remove from Deck link | `.copy-remove-deck` | `<a>` | Shown when copy is in a deck. Red text link. `data-copy-id` and `data-deck-id` attributes. |
| Move to Binder dropdown | `.copy-move-to-binder` | `<select>` | Shown when copy is in a deck. Lists all binders plus "New Binder...". `data-copy-id` attribute. |
| Remove from Binder link | `.copy-remove-binder` | `<a>` | Shown when copy is in a binder. Red text link. `data-copy-id` and `data-binder-id` attributes. |
| Move to Deck dropdown | `.copy-move-to-deck` | `<select>` | Shown when copy is in a binder. Lists all decks plus "New Deck...". `data-copy-id` attribute. |
| History toggle button | `.history-toggle` | `<button>` | Expands/collapses the status+movement history timeline for this copy. Text toggles between "History (down arrow)" and "History (up arrow)". `data-copy-id` attribute. |

---

## 4. User Flows

### 4.1 View Card Details

1. User navigates to `/card/:set/:cn`.
2. Page shows a loading spinner ("Loading card...").
3. JS extracts `set_code` and `collector_number` from the URL path.
4. Four parallel API calls fire: card data, settings, decks list, binders list.
5. On success, the layout renders: card image on the left, details panel on the right.
6. Page title updates to "{Card Name} -- DeckDumpster".
7. User sees: card name, oracle name (if different), mana cost icons, type line, mana value, set icon with set name and code, collector number, rarity, artist, treatment tags, external links (Scryfall/Card Kingdom with prices), Want button, Add button.

### 4.2 Flip Card Image

1. User clicks the flip button (circular arrow, bottom-right of card image).
2. Card image performs a 3D Y-axis rotation animation (0.6s CSS transition).
3. Front face is hidden; back face is revealed.
4. For double-faced cards (DFC layouts): the details panel re-renders with the back face's name, type line, and mana cost.
5. For non-DFC cards: the back shows the generic card back image; details panel does not change.
6. Clicking again flips back to the front.

### 4.3 Add Card to Wishlist

1. User clicks the "Want" button.
2. JS sends `POST /api/wishlist` with card name, set_code, and collector_number.
3. On success, button text changes to "Wanted" and gains green styling (class `wanted`).
4. Clicking "Wanted" again sends `DELETE /api/wishlist/:id`.
5. Button reverts to "Want" with default styling.

### 4.4 Add Card to Collection

1. User clicks the "Add" button.
2. An inline form appears below the action buttons with: date (pre-filled with today), price (empty), source (empty), and a "Confirm" button.
3. User optionally adjusts the date, enters a purchase price, and/or enters a source.
4. User clicks "Confirm".
5. Button text changes to "Adding..." and disables.
6. JS sends `POST /api/collection` with `printing_id`, `finish` (first from card's finishes array, defaulting to "nonfoil"), `acquired_at`, and optionally `purchase_price` and `source`.
7. On success: form closes, copies list reloads (new copy appears).
8. On failure: alert shows error message, button re-enables.
9. Clicking "Add" again while the form is open closes it (toggle behavior).

### 4.5 View Owned Copies

1. After page load, JS calls `GET /api/collection/copies?printing_id=:id`.
2. If copies exist, a "Copies (N)" section header appears followed by individual copy cards.
3. Each copy card shows: finish, condition, source, acquisition date, copy ID number.
4. Additional rows show (if applicable): order info (seller, order number, date), purchase price, sale price, image lineage actions (Reprocess/Refinish), and deck/binder assignment.
5. Active copies (owned/listed) show disposition controls at the bottom.

### 4.6 Dispose of a Copy

1. User selects a disposition from the "Dispose..." dropdown (Sold, Traded, Gifted, Lost, Listed, or Unlist).
2. Optionally enters a sale price and/or note.
3. Clicks the "Dispose" button.
4. JS sends `POST /api/collection/:id/dispose` with `new_status` and optional `sale_price` and `note`.
5. On success: copies list reloads showing the copy with its new disposition badge.
6. On failure: alert shows error, button re-enables.

### 4.7 Delete a Copy

1. User clicks the "Delete" button on a copy (only available for `owned` or `ordered` status).
2. Browser confirm dialog appears: "Delete copy #N? This cannot be undone."
3. If confirmed, JS sends `DELETE /api/collection/:id?confirm=true`.
4. On success: copies list reloads (copy removed).
5. On failure: alert shows error, button re-enables.

### 4.8 Receive an Ordered Copy

1. For copies with `status === 'ordered'`, a green "Receive" button appears in the copy header.
2. User clicks "Receive".
3. Button disables, text changes to "...".
4. JS sends `POST /api/collection/:id/receive`.
5. On success: copies list reloads (copy now shows as "owned").
6. On failure: button text changes to "Failed".

### 4.9 Assign Copy to Deck or Binder

**Unassigned copy:**
1. Two dropdowns appear: "Add to Deck" and "Add to Binder", each listing all existing decks/binders plus a "New Deck..."/"New Binder..." option.
2. Selecting an existing deck/binder sends `POST /api/decks/:id/cards` or `POST /api/binders/:id/cards` with the `collection_ids` array.
3. Selecting "New Deck..."/"New Binder..." prompts for a name, creates the container first, then assigns the copy.
4. On success: copies and container data reload.

**Copy in a deck:**
1. Deck name is shown with a red "Remove" link and a "Move to Binder" dropdown.
2. Clicking "Remove" sends `DELETE /api/decks/:id/cards` and reloads.
3. Selecting a binder from the dropdown sends `POST /api/binders/:id/cards/move` to atomically move the copy.

**Copy in a binder:**
1. Binder name is shown with a red "Remove" link and a "Move to Deck" dropdown.
2. Clicking "Remove" sends `DELETE /api/binders/:id/cards` and reloads.
3. Selecting a deck from the dropdown sends `POST /api/decks/:id/cards/move` to atomically move the copy.

### 4.10 Reprocess a Copy

1. User clicks "Reprocess" on a copy that has image lineage.
2. Confirm dialog warns that the card(s) from this image will be deleted and re-identified. If multiple copies share the same source image, the dialog says "ALL N cards."
3. If confirmed, JS sends `POST /api/ingest2/reset` with `image_id`.
4. On success: copies list reloads.
5. On failure: alert shows error.

### 4.11 Refinish a Copy

1. User clicks "Refinish" on a copy that has image lineage.
2. Confirm dialog warns that the card will be removed so the user can fix the finish.
3. If confirmed, JS sends `POST /api/ingest2/refinish` with `image_id`.
4. On success: copies list reloads.
5. On failure: alert shows error.

### 4.12 View Copy History

1. User clicks the "History" toggle button on a copy.
2. JS sends `GET /api/collection/:id/history`.
3. A timeline appears below the copy card showing chronological events:
   - **Status events**: e.g., "owned -> sold" with date and optional note. Green dot indicator.
   - **Movement events**: e.g., "Added to deck: My Deck (mainboard)", "Removed from binder: Trades", "Moved from deck X to binder Y". Blue dot indicator.
4. Clicking "History" again collapses the timeline.

### 4.13 Browse Price History

1. On page load, JS calls `GET /api/price-history/:set/:cn`.
2. If price data exists, the "Price History" section becomes visible.
3. A Chart.js line chart renders with up to 4 series: TCG Normal, TCG Foil, CK Buy Normal, CK Buy Foil.
4. Range pills (1M, 3M, 6M, 1Y, ALL) filter the time window. Pills for ranges exceeding available data are disabled (dimmed, non-clickable).
5. The first non-disabled pill is auto-selected.
6. Hovering over the chart shows a tooltip with date and price for all series at that point, plus a vertical crosshair line.
7. Dashed green horizontal lines indicate purchase prices of owned copies (if any).
8. Clicking a range pill re-filters and updates the chart.

---

## 5. Dynamic Behavior

### Initial Data Loading

All data is fetched asynchronously on page load. The HTML is a minimal shell with a loading spinner; the entire details panel is built in JS.

- **Parallel fetch on load**: `GET /api/card/by-set-cn`, `GET /api/settings`, `GET /api/decks`, `GET /api/binders`
- **Sequential after card loads**: `GET /api/wishlist?name=...` (to check wishlist state)
- **After render**: `GET /api/collection/copies?printing_id=...` (copies list), `GET /api/price-history/:set/:cn` (chart data)
- **Price chart also fetches**: `GET /api/collection/copies?printing_id=...` again (for purchase price reference lines)

### DOM Construction

The entire page content is built via `innerHTML` assignment in JavaScript. The HTML template contains only the layout container and a loading state div. After data loads:

1. `layout.innerHTML` is set with the image section and empty details panel.
2. `renderDetails(faceIdx)` populates the details panel.
3. `loadCopies()` populates the copies container asynchronously.
4. `renderPriceChart()` builds the Chart.js chart asynchronously.

### Re-rendering on Interaction

- **Flip**: Toggles CSS class `flipped` on `#card-flip`. For DFC cards, calls `renderDetails()` with the new face index (re-renders the entire details panel).
- **Want**: Toggles button text/class in-place; no panel re-render.
- **Add to collection**: Inline form is inserted/removed in `#add-form-container`. On success, calls `loadCopies()` which replaces `#copies-container` innerHTML.
- **Any copy action** (dispose, delete, receive, assign, reprocess, refinish): Calls `loadCopies()` to fully re-render the copies list. Assignment actions also call `loadContainerData()` to refresh deck/binder lists.
- **Price range pill click**: Updates `_priceChart.data.datasets` and calls `_priceChart.update()`. No DOM re-render.

### External Libraries

- **Chart.js 4** (via CDN): Line chart for price history.
- **chartjs-adapter-date-fns 3** (via CDN): Time scale adapter for Chart.js.
- **Keyrune** (via CDN): Set symbol icon font (`.ss` classes).
- **Mana Font** (via CDN): Mana cost icon font (`.ms` classes).

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Purpose |
|----------|--------|------|---------|
| `/api/card/by-set-cn?set=X&cn=Y` | GET | Page load | Fetch card/printing data. Required for page to function. |
| `/api/settings` | GET | Page load | Fetch user settings. Failure is non-fatal (defaults to `{}`). |
| `/api/decks` | GET | Page load + after assignments | Fetch all decks for assignment dropdowns. Failure is non-fatal. |
| `/api/binders` | GET | Page load + after assignments | Fetch all binders for assignment dropdowns. Failure is non-fatal. |
| `/api/wishlist?name=X` | GET | After card loads | Check if card is on wishlist. Failure is non-fatal. |
| `/api/wishlist` | POST | Want button click | Add card to wishlist. Body: `{name, set_code, collector_number}`. |
| `/api/wishlist/:id` | DELETE | Want button click (unwant) | Remove card from wishlist. |
| `/api/collection` | POST | Add confirm click | Add card to collection. Body: `{printing_id, finish, acquired_at, purchase_price?, source?}`. |
| `/api/collection/copies?printing_id=X` | GET | After render + after add/dispose/delete | Fetch all collection copies of this printing. |
| `/api/collection/:id/dispose` | POST | Dispose button click | Change copy status. Body: `{new_status, sale_price?, note?}`. |
| `/api/collection/:id?confirm=true` | DELETE | Delete button click | Permanently delete a copy. |
| `/api/collection/:id/receive` | POST | Receive button click | Mark ordered copy as received. |
| `/api/collection/:id/history` | GET | History toggle click | Fetch combined status + movement history for a copy. |
| `/api/price-history/:set/:cn` | GET | After render | Fetch price time series data. |
| `/api/decks/:id/cards` | POST | Deck assignment | Add copy to deck. Body: `{collection_ids, zone: "mainboard"}`. |
| `/api/decks/:id/cards` | DELETE | Remove from deck | Remove copy from deck. Body: `{collection_ids}`. |
| `/api/decks/:id/cards/move` | POST | Move to deck (from binder) | Atomically move copy to deck. Body: `{collection_ids, zone: "mainboard"}`. |
| `/api/decks` | POST | "New Deck..." option | Create a new deck. Body: `{name}`. |
| `/api/binders/:id/cards` | POST | Binder assignment | Add copy to binder. Body: `{collection_ids}`. |
| `/api/binders/:id/cards` | DELETE | Remove from binder | Remove copy from binder. Body: `{collection_ids}`. |
| `/api/binders/:id/cards/move` | POST | Move to binder (from deck) | Atomically move copy to binder. Body: `{collection_ids}`. |
| `/api/binders` | POST | "New Binder..." option | Create a new binder. Body: `{name}`. |
| `/api/ingest2/reset` | POST | Reprocess button click | Reset image for re-identification. Body: `{image_id}`. |
| `/api/ingest2/refinish` | POST | Refinish button click | Reset image for finish correction. Body: `{image_id}`. |

### Required Data for Page to Function

- The card must exist in the local database (printings table) with a matching `set_code` and `collector_number`.
- If the card API returns a non-OK response, the page shows an error state and stops.

---

## 7. Visual States

### 7.1 Loading State

- Visible: spinner icon + "Loading card..." text centered in the layout.
- Element: `#loading-state` div inside `#card-detail-layout`.
- Shown immediately on page load, replaced when data arrives.

### 7.2 Error State — Invalid URL

- If the URL does not match `/card/:set/:cn` pattern.
- Shows: "Invalid card URL. Expected /card/:set/:cn" in an `.empty-state` div.
- Replaces the loading state.

### 7.3 Error State — Card Not Found

- If `GET /api/card/by-set-cn` returns non-OK.
- Shows: the error message from the API (or "Card not found") in an `.empty-state` div.
- Replaces the loading state.

### 7.4 Loaded State — No Copies

- Card image and details panel are fully rendered.
- The copies container (`#copies-container`) is empty (no "Copies" section header).
- Want button shows "Want" (default) or "Wanted" (if on wishlist).
- Add button is available.
- Price chart section is hidden (default) or visible if price data exists.

### 7.5 Loaded State — With Copies

- Same as above, plus a "Copies (N)" section with individual copy cards.
- Each active copy shows disposition controls and assignment dropdowns.
- Each copy has a collapsible history toggle.

### 7.6 Loaded State — Price Chart Visible

- The `.price-chart-section` gains class `visible` (changes `display: none` to `display: block`).
- Chart renders with up to 4 colored lines.
- Range pills that exceed available data span are dimmed with class `disabled`.
- The first valid range pill is auto-selected with class `active`.

### 7.7 Loaded State — Price Chart Hidden

- If `GET /api/price-history` returns no data (all series empty), the chart section remains hidden (`display: none`).

### 7.8 Add Form Expanded

- The `#add-form-container` contains the `.add-collection-form` div with date, price, source inputs and confirm button.
- Triggered by clicking the Add button.

### 7.9 Add Form — Submitting

- The confirm button shows "Adding..." and is disabled.
- Inputs remain visible but the button is non-interactive.

### 7.10 Copy History Expanded

- The `#history-:id` container shows a `.history-timeline` with a left border and event dots.
- Status events have green dot indicators; movement events have blue dot indicators.
- The toggle button arrow points up.

### 7.11 Copy History — Loading

- Shows "Loading..." text in the history container.

### 7.12 Copy History — Empty

- Shows "No history" text if no events exist.

### 7.13 Copy History — Error

- Shows "Failed to load history" in red text.

### 7.14 Copies — Load Error

- Shows "Failed to load copies" in red text in the copies container.

### 7.15 Disposition Badges (Inactive Copies)

- Sold: green badge
- Traded: yellow badge
- Gifted: blue badge
- Lost: red badge
- Listed: purple badge

Each badge may include the date and note of the last status log entry.

### 7.16 Responsive Layout (Mobile)

- Below 768px viewport width, the layout switches from side-by-side to stacked (column direction).
- Card image section gets reduced padding; image width becomes 70vw instead of fixed 72vh height.
- Details panel loses its max-height constraint.

### 7.17 Card Flipped State

- The `.card-flip-container` has class `flipped`.
- CSS `transform: rotateY(180deg)` shows the back face.
- For DFC: details panel shows back face metadata.
- For non-DFC: back shows the generic card back image (`/static/card_back.jpeg`).

### 7.18 Wishlist Active State

- The Want button has class `wanted`, text "Wanted", green background (#1a5c3a), green text (#7ee8b0).
- On hover: accent red background and white text.
