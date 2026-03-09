# Sealed Products Page UX Description

**URL:** `/sealed`
**Source:** `mtg_collector/static/sealed.html`
**Title:** `Sealed Collection`

---

## 1. Page Purpose

The Sealed Products page is a dedicated inventory management interface for sealed Magic: The Gathering products (booster boxes, booster packs, bundles, commander decks, starter kits, etc.). Users can browse their sealed collection in either a visual grid or tabular view, filter and sort by various criteria (set, category, status, price, date), add new sealed products to their collection, edit or dispose of existing entries (sell, trade, gift, list, open), and "open" sealed products to automatically add their known card contents to the card collection. The page aggregates multiple collection entries of the same product into a single display row, showing combined quantities, cost ranges, and status breakdowns.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| `Sealed Collection` (header h1) | Link (`<a href="/">`) | `/` (home page) | Site title, always visible in header |
| `TCGPlayer` link (detail modal) | External link | TCGPlayer product page | Opens in new tab, only shown if `purchase_url_tcgplayer` exists |
| `Card Kingdom` link (detail modal) | External link | Card Kingdom product page | Opens in new tab, only shown if `purchase_url_cardkingdom` exists |

There is no global navigation bar or links to other pages (collection, decks, binders, etc.) on this page. The only site-level navigation is the header title linking back to the home page.

---

## 3. Interactive Elements

### Header Controls

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Search input | `#search-input` | `<input type="text">` | Placeholder: "Search collection..." -- filters products by name with 200ms debounce. Client-side filtering. |
| Add button | `#add-btn` | `<button>` | Text: "+ Add" -- opens the Add Product modal |
| Open Product button | `#open-btn` | `<button class="secondary">` | Text: "Open Product" -- opens the Open Product modal |
| Filters button | `#filter-btn` | `<button class="secondary">` | Text: "Filters" -- toggles the sidebar filter panel |
| Table view button | `#view-table-btn` | `<button class="secondary">` | SVG icon (three horizontal lines). Switches to table view. Has `.active` class when table view is selected. |
| Grid view button | `#view-grid-btn` | `<button class="secondary">` | SVG icon (four squares). Switches to grid view. Has `.active` class when grid view is selected. Default view. |
| Status text | `#status` | `<div>` | Displays entry count, quantity, total cost, market value, and gain/loss. |
| Prices status | `#prices-status` | `<span class="prices-status">` | Clickable text showing price freshness (e.g. "Prices: today", "Prices: 3d ago", "Prices: not loaded"). Click triggers price fetch via POST. |

### Sidebar Filter Panel (left slide-out, `#sidebar`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Sidebar backdrop | `#sidebar-backdrop` | `<div>` | Semi-transparent overlay, click to close sidebar |
| Set search input | `#set-search` | `<input type="text">` | Placeholder: "Search sets..." -- multi-select dropdown for filtering by set |
| Set dropdown | `#set-dropdown` | `<ul class="multi-dropdown">` | Dynamically populated list of sets, appears on focus/input |
| Set pills | `#set-pills` | `<div class="selected-pills">` | Shows selected set filter pills with "x" remove buttons |
| Category pills | `#category-pills` | `<div class="pill-group">` | Checkbox pills for: Booster Box, Booster Pack, Booster Case, Bundle, Bundle Case, Box Set, Deck, Commander Deck, Starter Kit, Limited Aid Tool, Case, Other |
| Status pills | `#status-pills` | `<div class="pill-group">` | Checkbox pills for: Owned, Listed, Opened, Sold, Traded, Gifted |
| Price min | `#price-min` | `<input type="number">` | Minimum purchase price filter, step 0.01 |
| Price max | `#price-max` | `<input type="number">` | Maximum purchase price filter, step 0.01 |
| Date min | `#date-min` | `<input type="date">` | Minimum date-added filter |
| Date max | `#date-max` | `<input type="date">` | Maximum date-added filter |
| Clear Filters button | `#clear-filters-btn` | `<button class="secondary">` | Text: "Clear Filters" -- resets all filter controls and re-renders |

Each category pill is a hidden checkbox + label pair with IDs like `#cat-booster_box`, `#cat-booster_pack`, etc.
Each status pill is a hidden checkbox + label pair with IDs like `#status-owned`, `#status-listed`, etc.

### Column Configuration Drawer (right slide-out, `#col-drawer`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Column config header (table) | `#col-config-th` | `<th>` | Gear-like SVG icon in the first column header of the table. Click to toggle column drawer. |
| Column drawer backdrop | `#col-drawer-backdrop` | `<div>` | Transparent overlay, click to close drawer |
| Column config list | `#col-config-list` | `<div>` | Checkbox list for toggling visible columns |
| Column checkboxes | `#cc-qty`, `#cc-image`, `#cc-name`, `#cc-set`, `#cc-min_cost`, `#cc-max_cost`, `#cc-avg_cost`, `#cc-market`, `#cc-added`, `#cc-status` | `<input type="checkbox">` | Toggle individual columns on/off. Default on: qty, image, name, set, min_cost, market. |

### Grid View Controls (visible only in grid mode)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Sort buttons | `.sort-btn` (no unique IDs) | `<span>` | Clickable sort buttons in sort bar, one per visible column. Data attribute `data-sort` holds the column key. |
| Grid size slider | `#grid-size-slider` | `<input type="range">` | Min: 120, Max: 400, controls `--grid-card-width` CSS variable. Value persisted in localStorage as `sealedGridCardSize`. |

### Table View Controls (visible only in table mode)

| Element | Type | Description |
|---------|------|-------------|
| Table headers `<th data-col="...">` | `<th>` | Clickable column headers to sort. Each has a `data-col` attribute matching the column key. Clicking toggles sort direction. |

### Detail/Edit Modal (`#detail-modal-overlay`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Detail overlay | `#detail-modal-overlay` | `<div>` | Dark backdrop overlay. Click outside modal to close. |
| Detail close button | `#detail-close` | `<button class="modal-close">` | "x" button in top-right corner |
| Detail image pane | `#detail-img-pane` | `<div>` | Product image display |
| Detail details pane | `#detail-details-pane` | `<div>` | Scrollable details content |
| Price history section | `#price-history-section` | `<div>` | Initially hidden, shown when price history loads successfully |
| Price history body | `#price-history-body` | `<div>` | Table of historical prices |

**Per-entry controls inside the detail modal** (dynamically generated for each collection entry):

| Element | Class/ID | Type | Description |
|---------|----------|------|-------------|
| Edit toggle | `.entry-edit-toggle` | `<button class="secondary">` | Toggles edit pane visibility. Text changes between "Edit" and "Close". Data attribute `data-idx`. |
| Edit pane | `#entry-edit-{idx}` | `<div class="entry-edit-pane">` | Collapsible edit form for each entry |
| Quantity input | `.ee-qty` | `<input type="number">` | Entry quantity, min 1 |
| Condition select | `.ee-condition` | `<select>` | Options: Near Mint, Lightly Played, Moderately Played, Heavily Played, Damaged |
| Price input | `.ee-price` | `<input type="number">` | Purchase price, step 0.01 |
| Date input | `.ee-date` | `<input type="date">` | Purchase date |
| Source input | `.ee-source` | `<input type="text">` | Placeholder: "e.g. TCGPlayer, LGS" |
| Seller input | `.ee-seller` | `<input type="text">` | Placeholder: "Store name" |
| Notes textarea | `.ee-notes` | `<textarea>` | Placeholder: "Optional notes" |
| Save button | `.entry-save-btn` | `<button>` | Saves entry edits via PUT. Data attributes: `data-entry-id`, `data-idx`. |
| Dispose status select | `.ee-dispose-status` | `<select>` | Available transitions based on current status. Owned can go to: sold, traded, gifted, listed, opened. Listed can go to: sold, traded, gifted, owned. |
| Dispose price input | `.ee-dispose-price` | `<input type="number">` | Sale price for disposition, step 0.01 |
| Dispose button | `.entry-dispose-btn` | `<button class="dispose-btn">` | Text: "Dispose" -- changes status with optional sale price. Data attributes: `data-entry-id`, `data-idx`. |
| Delete button | `.entry-delete-btn` | `<button class="delete-btn">` | Text: "Delete" -- prompts confirmation dialog, then deletes entry. Data attribute: `data-entry-id`. |

### Add Product Modal (`#add-modal-overlay`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Add overlay | `#add-modal-overlay` | `<div>` | Dark backdrop overlay. Click outside to close. |
| Add close button | `#add-close` | `<button class="modal-close">` | "x" button |
| Add search input | `#add-search-input` | `<input type="text">` | Placeholder: "Search sealed products by name..." -- debounced 300ms product search |
| TCGPlayer URL input | `#tcg-url-input` | `<input type="text">` | Placeholder: "Or paste TCGPlayer URL / product ID..." |
| TCGPlayer look up button | `#tcg-url-btn` | `<button class="secondary">` | Text: "Look Up" -- resolves TCGPlayer URL or product ID to a sealed product |
| Product results list | `#product-results` | `<ul class="product-results">` | Search results, each item clickable to select |
| Add modal body | `#add-modal-body` | `<div>` | Container that switches between search results and add form |

**Add form controls** (shown after product selection):

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Change product button | `#change-product-btn` | `<button class="secondary">` | Text: "Change" -- returns to product search |
| Quantity input | `#add-qty` | `<input type="number">` | Default: 1, min 1 |
| Condition select | `#add-condition` | `<select>` | Options: Near Mint (default), Lightly Played, Moderately Played, Heavily Played, Damaged |
| Price input | `#add-price` | `<input type="number">` | Placeholder: "Total purchase price", step 0.01 |
| Date input | `#add-date` | `<input type="date">` | Default: today's date |
| Source input | `#add-source` | `<input type="text">` | Placeholder: "e.g. TCGPlayer, LGS, Amazon" |
| Seller input | `#add-seller` | `<input type="text">` | Placeholder: "Store or seller name" |
| Notes textarea | `#add-notes` | `<textarea>` | Placeholder: "Optional notes" |
| Cancel button | `#cancel-add-btn` | `<button class="secondary">` | Text: "Cancel" -- closes modal |
| Confirm add button | `#confirm-add-btn` | `<button>` | Text: "Add to Collection" -- POSTs the new entry |

### Open Product Modal (`#open-modal-overlay`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Open overlay | `#open-modal-overlay` | `<div>` | Dark backdrop overlay. Click outside to close. |
| Open close button | `#open-close` | `<button class="modal-close">` | "x" button |
| Open modal title | `#open-modal-title` | `<h2>` | Text changes: "Open Sealed Product" initially, then "Open: {product name}" after selection |
| Open search input | `#open-search-input` | `<input type="text">` | Placeholder: "Search sealed products by name..." -- debounced 300ms |
| Open product results | `#open-product-results` | `<ul class="product-results">` | Search results. Products without contents data shown at 50% opacity with "No contents data" badge, and are not clickable. |
| Open modal body | `#open-modal-body` | `<div>` | Container that switches between search results and open preview |

**Open preview controls** (shown after selecting a product with contents):

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Condition select | `#open-condition` | `<select>` | Options: Near Mint (default), Lightly Played, Moderately Played, Heavily Played, Damaged |
| Track checkbox | `#open-track` | `<input type="checkbox">` | Label: "Add to sealed collection as 'opened'" -- toggles purchase price/date fields |
| Purchase price input | `#open-price` | `<input type="number">` | Hidden by default, shown when "Track" is checked. Step 0.01. |
| Purchase price row | `#open-price-row` | `<div class="form-row">` | Container for price input, display toggled by track checkbox |
| Purchase date input | `#open-date` | `<input type="date">` | Hidden by default, shown when "Track" is checked. Default: today. |
| Purchase date row | `#open-date-row` | `<div class="form-row">` | Container for date input, display toggled by track checkbox |
| Back button | `#open-back-btn` | `<button class="secondary">` | Text: "Back" -- returns to product search |
| Confirm open button | `#open-confirm-btn` | `<button>` | Text: "Open & Add {N} Cards" -- POSTs to open the product. Disabled during request with text "Opening..." |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Escape | Closes the topmost open overlay in order: detail modal > open modal > add modal > column drawer > filter sidebar |

---

## 4. User Flows

### Flow 1: Browse Sealed Collection

1. Page loads and fetches collection data from `/api/sealed/collection` and `/api/sealed/collection/stats`
2. Products are aggregated by `sealed_product_uuid` -- entries with the same UUID are grouped into one display row
3. Default view is grid (or last-used view from localStorage `sealedViewMode`)
4. Default sort is `added_at` descending (newest first)
5. Status bar shows: "{N} entries, {N} items, ${X} invested, ${X} market value, +/-${X}"
6. Each product card/row shows: image, set name, category, quantity badge (if >1), status badge, cost, market price

### Flow 2: Search Collection

1. User types in the `#search-input` field
2. After 200ms debounce, client-side filter runs against product `name` field (case-insensitive substring match)
3. Grid/table re-renders with matching products only
4. Empty state shows "No entries match your filters." if no results

### Flow 3: Filter by Sidebar

1. User clicks "Filters" button to open the left sidebar
2. Sidebar slides in from the left with backdrop overlay
3. User selects filters: set (multi-select searchable dropdown), category pills, status pills, price range, date range
4. Each filter change triggers immediate re-render (no apply button needed)
5. User clicks "Clear Filters" to reset all filters
6. User clicks backdrop or presses Escape to close sidebar

### Flow 4: Switch View Mode

1. User clicks table or grid icon button in header
2. View mode switches immediately
3. Selected mode is persisted to localStorage (`sealedViewMode`)
4. Grid view shows: sort bar at top + card grid with images, names, prices
5. Table view shows: sortable column headers + tabular data with small thumbnails

### Flow 5: Sort Products

- **Grid view:** Click sort buttons in the sort bar above the grid. Active sort shows arrow indicator.
- **Table view:** Click column headers (`<th>`). Active column shows arrow indicator and highlighted color.
- Clicking the active sort column toggles direction (asc/desc). Clicking a different column sets it as the new sort key (text columns default asc, numeric/date columns default desc).

### Flow 6: Resize Grid Cards

1. In grid view, a "Size" range slider appears in the sort bar
2. User drags slider between 120px and 400px
3. Card width updates in real-time via CSS custom property `--grid-card-width`
4. Value persisted to localStorage (`sealedGridCardSize`)

### Flow 7: Configure Table Columns

1. In table view, user clicks the column config icon (grid-like SVG) in the first header cell
2. Column drawer slides in from the right
3. User checks/unchecks columns: Qty, (image), Set, Type, Min Cost, Max Cost, Avg Cost, Market, Added, Status
4. Table re-renders immediately on each change
5. Column preferences persisted to localStorage (`sealedCols`)
6. Click backdrop or Escape to close drawer

### Flow 8: View Product Detail

1. User clicks a product card (grid) or table row
2. Detail modal opens with dark overlay
3. Left pane shows product image (if available)
4. Right pane shows:
   - Product name
   - Product section: Set, Category, Subtype, Release date, Card count, Total quantity
   - Cost section (if any entries have prices): Min, Max, Avg per unit
   - Market price section (if prices loaded): Total, Low, Mid, High
   - Price history table (loaded async, if product has `tcgplayer_product_id`)
   - Contents breakdown (parsed from `contents_json`): sealed sub-products, decks, cards, other items
   - Entries section: one collapsible row per collection entry with status badge, cost, condition, source, date
   - Links section: TCGPlayer, Card Kingdom links (if available)
5. Close via "x" button, clicking outside modal, or Escape key

### Flow 9: Edit a Collection Entry

1. Open detail modal for a product (Flow 8)
2. Click "Edit" on a specific entry row
3. Edit pane expands showing: Quantity, Condition, Price, Date, Source, Seller, Notes fields
4. Modify any fields
5. Click "Save" -- PUTs update to `/api/sealed/collection/{id}`
6. On success: modal closes, collection re-fetches and re-renders

### Flow 10: Dispose of a Collection Entry

1. Open detail modal and expand an entry's edit pane (Flow 9)
2. Select a disposition status from the dropdown (available transitions depend on current status):
   - From `owned`: sold, traded, gifted, listed, opened
   - From `listed`: sold, traded, gifted, owned
3. Optionally enter a sale price
4. Click "Dispose" -- POSTs to `/api/sealed/collection/{id}/dispose`
5. On success: modal closes, collection re-fetches

### Flow 11: Delete a Collection Entry

1. Open detail modal and expand an entry's edit pane
2. Click "Delete" button (red)
3. Browser confirmation dialog: "Delete this sealed collection entry? This cannot be undone."
4. If confirmed: DELETEs `/api/sealed/collection/{id}?confirm=true`
5. On success: modal closes, collection re-fetches

### Flow 12: Add a Product via Name Search

1. Click "+ Add" button in header
2. Add modal opens, search input is auto-focused
3. Type at least 2 characters in "Search sealed products by name..."
4. After 300ms debounce, results load from `/api/sealed/products?q={query}&limit=20`
5. Results show: thumbnail, product name, set name, category
6. Click a result to select it
7. Add form appears with the selected product shown and fields: Quantity (1), Condition (Near Mint), Price, Date (today), Source, Seller, Notes
8. "Change" button returns to search
9. Fill in desired fields
10. Click "Add to Collection" -- POSTs to `/api/sealed/collection`
11. On success: modal closes, collection re-fetches

### Flow 13: Add a Product via TCGPlayer URL

1. Click "+ Add" button in header
2. Paste a TCGPlayer URL or product ID into the "Or paste TCGPlayer URL / product ID..." input
3. Click "Look Up" (or press Enter)
4. POSTs to `/api/sealed/from-tcgplayer` with `{ url: "..." }`
5. If found: shows the add form (same as Flow 12 step 7)
6. If not found: input border flashes red for 2 seconds

### Flow 14: Open a Sealed Product

1. Click "Open Product" button in header
2. Open modal appears, search input auto-focused
3. Search for a product (same mechanics as Flow 12)
4. Results show: thumbnail, name, set, category. Products without contents data are dimmed (50% opacity) with a "No contents data" badge and are not clickable.
5. Click a product that has contents data
6. Modal title changes to "Open: {product name}", search input hides
7. Open preview shows:
   - Summary badges: "{N} cards to add", "{N} unresolvable" (warning), "{N} sealed sub-products", "{N} other items (skipped)"
   - Card table(s) grouped by source name, each with columns: Card, Set, Qty, Finish
   - Sealed sub-products list (if any)
   - Options: Condition dropdown, "Track product" checkbox
8. If "Track product" is checked, additional fields appear: Purchase price, Purchase date
9. Click "Open & Add {N} Cards"
10. Button disables and shows "Opening..."
11. POSTs to `/api/sealed/open`
12. On success: modal closes, collection re-fetches, status bar briefly shows "Added {N} cards from {product name}"
13. On failure: button re-enables, alert shown with error message
14. "Back" button returns to product search

### Flow 15: Fetch/Refresh Prices

1. Prices status indicator in the header shows: "Prices: today", "Prices: Xd ago", "Prices: not loaded", or "Prices: unavailable"
2. Click the prices status text
3. Text changes to "Prices: fetching..." with red color
4. POSTs to `/api/sealed/fetch-prices`
5. On success: collection re-fetches, prices status updates
6. On error: shows "Prices: error"

---

## 5. Dynamic Behavior

### On Page Load (Async Init)

1. `initFilters()` -- populates category and status pill groups from hardcoded arrays
2. `initEventListeners()` -- wires up all event handlers
3. Restores grid card size from localStorage (`sealedGridCardSize`), default 220px
4. `fetchCollection()` -- parallel fetches of `/api/sealed/collection` and `/api/sealed/collection/stats`
5. `fetchSets()` -- fetches `/api/sealed/products/sets` for the set filter dropdown (fire-and-forget, does not block render)
6. `loadPricesStatus()` -- fetches `/api/sealed/prices-status` to display price freshness

### Client-Side Filtering

All filtering is done client-side after the initial data fetch. The filter pipeline:
1. `refilterAndRender()` collects all current filter values
2. Filters `allEntries` array by: search query (name substring), selected sets, checked categories, checked statuses, price range, date range
3. Builds `aggregatedProducts` via `buildAggregatedProducts()` which groups entries by `sealed_product_uuid` and computes: total quantity, min/max/avg cost, market total, status counts, primary status, earliest added_at
4. Applies sort via `applySort()`
5. Calls `render()` to build HTML

### View Mode Rendering

- `render()` delegates to `renderGrid()` or `renderTable()` based on `viewMode`
- After innerHTML replacement, event listeners are re-attached for: sort buttons, table headers, column config, size slider, card/row clicks
- Grid cards use `[data-uuid]` attribute; table rows use `[data-uuid]` attribute

### Multi-Select Dropdown

The set filter uses a reusable `initMultiSelect()` component:
- On focus/input: renders a filtered dropdown of up to 50 items, positioned absolutely relative to the input
- On blur: closes dropdown after 150ms delay (to allow click events)
- On item click: toggles selection, updates pills, re-filters
- Selected items shown as pills with "x" remove buttons

### Detail Modal Async Loading

When a detail modal opens:
- If the product has a `tcgplayer_product_id`, price history is fetched asynchronously from `/api/sealed/prices/{tcgplayer_product_id}`
- The `#price-history-section` is initially hidden (`display: none`), shown only if price data returns successfully
- Price history table shows columns: Date, Low, Mid, Market, High

### Open Product Preview Async Loading

When a product is selected in the Open modal:
- Contents are fetched from `/api/sealed/products/{uuid}/contents`
- Loading state shows "Loading contents..."
- If product is not openable, shows error message with "Back" button
- If openable, shows card table and options

### LocalStorage Persistence

| Key | Default | Description |
|-----|---------|-------------|
| `sealedViewMode` | `'table'` | Current view mode: `'grid'` or `'table'` |
| `sealedCols` | `['qty','image','name','set','min_cost','market']` | Enabled table columns (JSON array) |
| `sealedGridCardSize` | `'220'` | Grid card width in pixels |

Note: The code initializes `viewMode` with `localStorage.getItem('sealedViewMode') || 'table'`, but the HTML has `#view-grid-btn` with class `active` by default. The JS corrects this on init by setting the correct active class based on `viewMode`.

### Stats Bar Updates

After each successful data modification (add, edit, dispose, delete, open, price fetch), `fetchCollection()` is called which re-fetches both the collection and stats, then updates the status bar with: entry count, quantity, total invested, market value, and gain/loss (colored green for gains, red for losses).

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When Called | Request Body | Response |
|----------|--------|-------------|--------------|----------|
| `/api/sealed/collection` | GET | Page load, after any mutation | -- | Array of sealed collection entries with product metadata |
| `/api/sealed/collection/stats` | GET | Page load, after any mutation | -- | `{ total_entries, total_quantity, by_status, total_cost, market_value, gain_loss }` |
| `/api/sealed/products/sets` | GET | Page load (once) | -- | Array of `{ set_code, set_name, product_count }` |
| `/api/sealed/prices-status` | GET | Page load (once) | -- | `{ available, last_date, product_count }` |
| `/api/sealed/products?q={query}&limit=20` | GET | Add modal search, Open modal search | -- | Array of product catalog entries with `has_contents` flag |
| `/api/sealed/from-tcgplayer` | POST | TCGPlayer URL lookup | `{ url: "..." }` | Product catalog entry (or error) |
| `/api/sealed/collection` | POST | Adding a product | `{ sealed_product_uuid, quantity, condition, purchase_price?, purchase_date?, source?, seller_name?, notes? }` | Created entry |
| `/api/sealed/collection/{id}` | PUT | Editing an entry | `{ quantity, condition, purchase_price, purchase_date, source, seller_name, notes }` | Updated entry |
| `/api/sealed/collection/{id}/dispose` | POST | Disposing an entry | `{ new_status, sale_price? }` | Updated entry |
| `/api/sealed/collection/{id}?confirm=true` | DELETE | Deleting an entry | -- | Success/error |
| `/api/sealed/prices/{tcgplayer_product_id}` | GET | Detail modal (async) | -- | Array of price history records |
| `/api/sealed/fetch-prices` | POST | Click prices status | `{}` | `{ ok: true/false }` |
| `/api/sealed/products/{uuid}/contents` | GET | Open product preview | -- | `{ openable, cards, total_cards, unresolvable, sealed_sub_products, other_items }` |
| `/api/sealed/open` | POST | Confirming product open | `{ sealed_product_uuid, condition, track_in_sealed, purchase_price?, purchase_date? }` | `{ cards_added }` |

### Data Requirements

- The page requires sealed product data in the database (populated via `mtg setup` / MTGJSON import)
- The sealed products catalog (`sealed_products` table) must be populated for the Add and Open flows to work
- Contents data (`sealed_product_cards` table) must be populated for the Open Product flow to resolve cards
- Price data is optional -- if not fetched, market-related columns and sections are simply empty

---

## 7. Visual States

### Page-Level States

| State | Condition | Display |
|-------|-----------|---------|
| Loading | Initial page load before data arrives | Main area shows: "Loading..." (italic, centered, gray) |
| Empty collection | `allEntries.length === 0` after data loads | Main area shows: "No sealed products in your collection yet. Click '+ Add' to get started." |
| No filter matches | Filters active but no entries match | Main area shows: "No entries match your filters." |
| Grid view (populated) | `viewMode === 'grid'` with products | Sort bar + card grid. Cards show: image (or "no image" placeholder), quantity badge (if >1), status badge, set name, category, market price, cost. |
| Table view (populated) | `viewMode === 'table'` with products | Sortable table with configurable columns. Column config icon in first header cell. |

### Product Card Visual States (Grid)

| State | Visual |
|-------|--------|
| Has image | Product image displayed in square container with `contain` fit |
| No image | Gray placeholder text showing product name |
| Quantity > 1 | Red badge in top-right corner showing "{N}x" |
| Status badge | Colored badge in top-left corner. Colors: owned=green, listed=purple, opened=orange, sold=dark-green, traded=dark-yellow, gifted=dark-blue |

### Status Badge Colors

| Status | Background | Text |
|--------|------------|------|
| `owned` | `rgba(76, 175, 80, 0.85)` (green) | white |
| `listed` | `rgba(130, 0, 255, 0.85)` (purple) | white |
| `opened` | `rgba(255, 152, 0, 0.85)` (orange) | white |
| `sold` | `rgba(26, 92, 58, 0.85)` (dark green) | light green |
| `traded` | `rgba(92, 74, 26, 0.85)` (dark yellow) | light yellow |
| `gifted` | `rgba(26, 58, 92, 0.85)` (dark blue) | light blue |

### Modal States

| Modal | States |
|-------|--------|
| Detail modal | Closed (hidden) / Open (visible with product data) |
| Add modal | Closed / Open-searching (search input + results list) / Open-form (selected product + add form) |
| Open modal | Closed / Open-searching (search input + results) / Open-loading ("Loading contents...") / Open-preview (card table + options) / Open-error (error message + back button) / Open-submitting (button disabled, "Opening...") |
| Filter sidebar | Closed (off-screen left) / Open (visible with backdrop) |
| Column drawer | Closed (off-screen right) / Open (visible with backdrop) |

### Prices Status States

| State | Text | Style |
|-------|------|-------|
| Loaded (recent) | "Prices: today" or "Prices: {N}d ago" | Default gray |
| Not loaded | "Prices: not loaded" | Default gray |
| Unavailable | "Prices: unavailable" | Default gray |
| Fetching | "Prices: fetching..." | Red color (`.loading` class) |
| Error | "Prices: error" | Default gray |

### Stats Bar Content Pattern

Format: `{N} entries . {N} items . ${X} invested . ${X} market value . {+/-}${X}`

- Gain/loss is colored green (`.gain`) if positive, red (`.loss`) if negative
- "invested" and "market value" parts are only shown if their values are > 0

### Responsive Behavior (max-width: 768px)

- Detail modal stacks vertically (image on top, details below)
- Image width becomes `70vw` instead of fixed height
- Search input narrows to 140px
- Add/Open modals take 95vw width

### Entry Edit Pane States

| State | Visual |
|-------|--------|
| Collapsed | Edit pane hidden (`display: none`), button shows "Edit" |
| Expanded | Edit pane visible with all form fields, button shows "Close" |

### TCGPlayer URL Lookup States

| State | Visual |
|-------|--------|
| Error | Input border color flashes to `#e87e7e` (red) for 2 seconds, then resets |
| Success | Transitions to add form with selected product |

### Open Product Result Item States

| State | Visual |
|-------|--------|
| Has contents | Normal opacity, clickable |
| No contents | 50% opacity, "No contents data" badge, not clickable (click handler returns early) |
