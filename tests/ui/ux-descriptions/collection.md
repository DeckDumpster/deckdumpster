# Collection Browser Page — UX Description

**URL:** `/collection`
**Source:** `mtg_collector/static/collection.html`
**Title:** Collection Browser

---

## 1. Page Purpose

The Collection Browser is the primary interface for viewing, searching, filtering, sorting, and managing all Magic: The Gathering cards in the user's collection. It provides three view modes (table, grid, and order-grouped), a comprehensive filter sidebar with 13 filter dimensions, a card detail modal with price history charts and per-copy management, multi-select operations for bulk actions (wishlist, deck/binder assignment, delete, share), a wishlist side panel, saved views, and integration with external vendors (Scryfall, TCGplayer, Card Kingdom). It also supports an "include unowned" mode that shows cards from sets the user does not own, enabling set completion tracking and buy-list generation.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| Header `<h1>` "Collection" | Link (`<a>`) | `/` | Returns to homepage |
| Modal "Full page" badge | Link (`<a>`) | `/card/:set/:cn` | Opens standalone card detail page |
| SF price badge (table/grid/modal) | External link | `https://scryfall.com/card/:set/:cn` | Opens Scryfall card page |
| CK price badge (table/grid/modal) | External link | Card Kingdom search URL | Opens Card Kingdom listing |
| Order "Edit" link (orders view) | Link (`<a>`) | `/edit-order?id=:orderId` | Edit order page |
| Deck name link in copy section | Link (`<a>`) | N/A (inline removal) | Remove from deck action |
| Wishlist panel CK button | External link | `https://www.cardkingdom.com/builder` | Opens CK deck builder (copies list to clipboard) |
| Wishlist panel TCG button | External link | `https://www.tcgplayer.com/massentry` | Opens TCG mass entry (copies list to clipboard) |

---

## 3. Interactive Elements

### 3.1 Header Controls

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Search input | `search-input` | `<input type="text">` | Free-text card name search. 220px wide. Placeholder: "Search cards...". Debounced 300ms, triggers server fetch. |
| Table view button | `view-table-btn` | `<button class="secondary">` | Switches to table/list view. Contains SVG icon (horizontal lines). Part of segmented toggle group. |
| Grid view button | `view-grid-btn` | `<button class="secondary">` | Switches to card image grid view. Contains SVG icon (4 squares). Part of segmented toggle group. |
| Orders view button | `view-orders-btn` | `<button class="secondary">` | Switches to order-grouped view. Contains SVG icon (envelope). Hidden when no ordered cards exist. Part of segmented toggle group. |
| Filters toggle button | `sidebar-toggle-btn` | `<button class="secondary">` | Opens/closes the filter sidebar (slide-in panel from left). Text: "Filters". |
| More menu button | `more-menu-btn` | `<button class="secondary">` | Vertical ellipsis button. Opens dropdown with additional options. |
| Grid column minus button | `col-minus` | `<button class="col-btn">` | Decreases grid column count. Min 1. Inside `grid-size-wrap`, visible only in grid view. |
| Grid column count display | `col-count` | `<div class="col-count">` | Shows current grid column count (1-12). |
| Grid column plus button | `col-plus` | `<button class="col-btn">` | Increases grid column count. Max 12. |
| Grid size wrapper | `grid-size-wrap` | `<div>` | Contains column +/- controls. `display:none` when not in grid view. |
| Status text | `status` | `<div>` | Shows card count and total value summary. Auto-updated on data changes. |

### 3.2 More Menu Dropdown (`more-menu-dropdown`)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Include unowned toggle | `include-unowned-btn` | `<button class="menu-item">` | Cycles through 3 states: off -> "base" (common printings) -> "full" (all printings) -> off. Disabled when no filters are active. Requires at least one set filter. |
| Buy Missing for CK | `buy-missing-ck` | `<button class="menu-item">` | Copies unowned card list for Card Kingdom format, opens CK builder. Only visible when include-unowned is active. |
| Buy Missing for TCG | `buy-missing-tcg` | `<button class="menu-item">` | Copies unowned card list for TCGplayer format, opens TCG mass entry. Only visible when include-unowned is active. |
| Wishlist toggle | `wishlist-toggle-btn` | `<button class="menu-item">` | Opens the wishlist side panel. Shows count: "Wishlist (N)". |
| Toggle Multi-Select | `toggle-multiselect-btn` | `<button class="menu-item">` | Enables/disables multi-card selection mode. Clears current selection when toggled. |
| Image Display pills | `image-display-pills` | `<div class="pill-row">` | Two pills: "Crop" and "Contain". Controls card thumbnail display mode. Persisted via `PUT /api/settings`. |
| Price Floor input | `price-floor-input` | `<input type="number">` | Sets minimum price threshold for value calculations. Step 0.01. Persisted via `PUT /api/settings`. |

### 3.3 Selection Bar (`selection-bar`)

Appears when multi-select mode is active. Fixed bar between header and content.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Selected count | `sel-count` | `<span>` | Displays "N selected". |
| Select All | `sel-all` | `<button class="sel-link">` | Selects all visible cards. |
| Select None | `sel-none` | `<button class="sel-link">` | Deselects all cards. |
| Share result area | `sel-share-result` | `<span>` | Shows share link or status messages after bulk operations. |
| Want button | `sel-want-btn` | `<button>` | Adds all selected cards to wishlist in bulk via `POST /api/wishlist/bulk`. |
| Share button | `sel-share-btn` | `<button>` | Generates a Scryfall search URL for selected cards, shortens it via `/api/shorten`, shows link. |
| Add to Deck button | `sel-deck-btn` | `<button>` | Opens deck assignment modal for selected cards. Calls `showAssignDeckModal()`. |
| Add to Binder button | `sel-binder-btn` | `<button>` | Opens binder assignment modal for selected cards. Calls `showAssignBinderModal()`. |
| Delete button | `sel-delete-btn` | `<button>` | Deletes all selected cards from collection. Confirms with dialog showing total quantity. Calls `POST /api/collection/bulk-delete`. |

### 3.4 Filter Sidebar (`sidebar`)

Slides in from the left. 300px wide. Contains all filter controls.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Close Filters button | `sidebar-close-btn` | `<button class="secondary">` | Closes the filter sidebar. |
| Sidebar backdrop | `sidebar-backdrop` | `<div>` | Semi-transparent overlay. Clicking it closes the sidebar. |
| **Saved Views** | | | |
| View select | `view-select` | `<select>` | Dropdown of saved filter configurations. First option: "-- None --". Loading a view applies its saved filters. |
| Save Current Filters | (inline) | `<button class="secondary">` | Prompts for a name, saves current filter state as a named view via `POST /api/views`. |
| **Color Filter** | `color-filters` | Pill group (checkboxes) | 6 pills: W, U, B, R, G, C (colorless). Uses mana font icons. Multi-select (AND logic: card must have all selected colors). Client-side filter. |
| `cf-W` | `cf-W` | `<input type="checkbox">` | White filter |
| `cf-U` | `cf-U` | `<input type="checkbox">` | Blue filter |
| `cf-B` | `cf-B` | `<input type="checkbox">` | Black filter |
| `cf-R` | `cf-R` | `<input type="checkbox">` | Red filter |
| `cf-G` | `cf-G` | `<input type="checkbox">` | Green filter |
| `cf-C` | `cf-C` | `<input type="checkbox">` | Colorless filter |
| **Rarity Filter** | `rarity-filters` | Pill group (checkboxes) | 4 pills: C, U, R, M with colored rarity dots. Client-side filter. |
| `rf-common` | `rf-common` | `<input type="checkbox">` | Common filter |
| `rf-uncommon` | `rf-uncommon` | `<input type="checkbox">` | Uncommon filter |
| `rf-rare` | `rf-rare` | `<input type="checkbox">` | Rare filter |
| `rf-mythic` | `rf-mythic` | `<input type="checkbox">` | Mythic filter |
| **Set Filter** | `set-filter-wrap` | Multi-select component | Searchable dropdown with pill display for selected sets. |
| Set search input | `set-search` | `<input type="text">` | Placeholder: "Search sets...". Filters dropdown as you type. Shows up to 50 results. |
| Set dropdown | `set-dropdown` | `<ul class="multi-dropdown">` | Dropdown list of matching sets. Items show "Name (CODE)". Selected items highlighted. |
| Set pills | `set-pills` | `<div class="selected-pills">` | Shows selected sets as removable pills. |
| **Type Filter** | `type-filters` | Pill group (checkboxes) | 10 pills: Creature, Instant, Sorcery, Enchantment, Artifact, PW (Planeswalker), Land, Battle, Kindred, Token. Client-side filter. |
| `tf-creature` | `tf-creature` | `<input type="checkbox">` | Creature type filter |
| `tf-instant` | `tf-instant` | `<input type="checkbox">` | Instant type filter |
| `tf-sorcery` | `tf-sorcery` | `<input type="checkbox">` | Sorcery type filter |
| `tf-enchantment` | `tf-enchantment` | `<input type="checkbox">` | Enchantment type filter |
| `tf-artifact` | `tf-artifact` | `<input type="checkbox">` | Artifact type filter |
| `tf-planeswalker` | `tf-planeswalker` | `<input type="checkbox">` | Planeswalker type filter |
| `tf-land` | `tf-land` | `<input type="checkbox">` | Land type filter |
| `tf-battle` | `tf-battle` | `<input type="checkbox">` | Battle type filter |
| `tf-kindred` | `tf-kindred` | `<input type="checkbox">` | Kindred type filter |
| `tf-token` | `tf-token` | `<input type="checkbox">` | Token type filter |
| **Subtype Filter** | `subtype-filter-wrap` | Multi-select component | Searchable dropdown for creature/spell subtypes (e.g., "Elf", "Dragon"). |
| Subtype search input | `subtype-search` | `<input type="text">` | Placeholder: "Search subtypes...". Filters dropdown. |
| Subtype dropdown | `subtype-dropdown` | `<ul class="multi-dropdown">` | Dropdown of subtypes extracted from loaded cards. |
| Subtype pills | `subtype-pills` | `<div class="selected-pills">` | Shows selected subtypes as removable pills. |
| **Collector Number Range** | | Range inputs | |
| CN Min | `cn-min` | `<input type="number">` | Minimum collector number. Debounced 150ms client-side filter. |
| CN Max | `cn-max` | `<input type="number">` | Maximum collector number. |
| **Mana Value Range** | | Range inputs | |
| CMC Min | `cmc-min` | `<input type="number">` | Minimum converted mana cost. Debounced 150ms client-side filter. |
| CMC Max | `cmc-max` | `<input type="number">` | Maximum converted mana cost. |
| **Finish Filter** | `finish-filters` | Pill group (checkboxes) | 3 pills: Nonfoil, Foil, Etched. Client-side filter. |
| `ff-nonfoil` | `ff-nonfoil` | `<input type="checkbox">` | Nonfoil finish filter |
| `ff-foil` | `ff-foil` | `<input type="checkbox">` | Foil finish filter |
| `ff-etched` | `ff-etched` | `<input type="checkbox">` | Etched finish filter |
| **Status Filter** | `status-filters` | Pill group (checkboxes) | 6 pills: Ordered, Wanted, Sold, Traded, Gifted, Lost. Ordered/Wanted are client-side. Sold/Traded/Gifted/Lost trigger server re-fetch with `status=all`. |
| `sf-ordered` | `sf-ordered` | `<input type="checkbox">` | Ordered status filter |
| `sf-wanted` | `sf-wanted` | `<input type="checkbox">` | Wanted (wishlist) status filter |
| `sf-sold` | `sf-sold` | `<input type="checkbox">` | Sold disposition filter (triggers server fetch) |
| `sf-traded` | `sf-traded` | `<input type="checkbox">` | Traded disposition filter (triggers server fetch) |
| `sf-gifted` | `sf-gifted` | `<input type="checkbox">` | Gifted disposition filter (triggers server fetch) |
| `sf-lost` | `sf-lost` | `<input type="checkbox">` | Lost disposition filter (triggers server fetch) |
| **Treatment Filter** | `badge-filters` | Pill group (checkboxes) | 5 pills: BL (Borderless), SC (Showcase), EA (Extended Art), FA (Full Art), Promo. Client-side filter. |
| `bf-borderless` | `bf-borderless` | `<input type="checkbox">` | Borderless treatment filter |
| `bf-showcase` | `bf-showcase` | `<input type="checkbox">` | Showcase treatment filter |
| `bf-extendedart` | `bf-extendedart` | `<input type="checkbox">` | Extended art treatment filter |
| `bf-fullart` | `bf-fullart` | `<input type="checkbox">` | Full art treatment filter |
| `bf-promo` | `bf-promo` | `<input type="checkbox">` | Promo treatment filter |
| **Price Range** | | Range inputs | |
| Price Min | `price-min` | `<input type="number">` | Minimum price (USD). Step 0.01. Debounced 150ms client-side filter. |
| Price Max | `price-max` | `<input type="number">` | Maximum price (USD). |
| **Date Added Range** | | Range inputs | |
| Date Min | `date-min` | `<input type="date">` | Earliest acquisition date. Debounced 150ms client-side filter. |
| Date Max | `date-max` | `<input type="date">` | Latest acquisition date. |
| **Container Filter** | `container-filter` | `<select>` | Dropdown: "All Cards", "Unassigned Only", plus optgroups for Decks and Binders. Shows card counts per container. Client-side filter. |
| Clear Filters button | `clear-filters-btn` | `<button>` | Resets all filters, clears search, resets include-unowned, and re-fetches collection. |

### 3.5 Column Configuration Drawer (`col-drawer`)

Slides in from the right. Contains checkboxes for toggling table columns.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Column config icon (table header) | `col-config-th` | `<th>` | Grid icon in table's first header cell. Clicking opens/closes column drawer. |
| Column drawer backdrop | `col-drawer-backdrop` | `<div>` | Semi-transparent overlay. Click to close. |
| Column config pill group | `col-config-dropdown` | `<div class="pill-group">` | Checkboxes for each column: Qty, Card, Type, Cost, Set, #, Price, Cond., Added, CK Buy $, TCG $. Saved to localStorage key `collectionCols`. |

Available columns (from `ALL_COLUMNS`):
- `qty` - Quantity (default on)
- `name` - Card name with thumbnail (default on)
- `type` - Type line (default on)
- `mana` - Mana cost with icons (default on)
- `set` - Set with Keyrune icon (default on)
- `collector_number` - Collector number (default on)
- `price` - Price badges with SF/CK links (default on)
- `condition` - Condition abbreviation (default off)
- `date_added` - Acquisition date (default off)
- `ck_price` - Card Kingdom buylist price (default off)
- `tcg_price` - TCGplayer price (default off)

### 3.6 Card Detail Modal (`card-modal-overlay`)

Full-screen overlay modal showing card details. Opened by clicking any card row/tile.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Modal overlay | `card-modal-overlay` | `<div>` | Full-screen semi-transparent backdrop. Click outside modal to close. |
| Modal close button | `modal-close` | `<button class="modal-close">` | X button in top-right corner. |
| Front card image | `modal-img-front` | `<img>` | Full-size card front image. |
| Back card image | `modal-img-back` | `<img>` | Back face for DFC cards, or card back image. |
| Flip container | `modal-flip` | `<div class="card-flip-container">` | 3D flip animation container. Toggles `flipped` class for 180-degree Y rotation. |
| Flip button | `modal-flip-btn` | `<button class="flip-btn">` | Circular button in bottom-right of image area. Flips card between front and back. |
| Modal details panel | `modal-details` | `<div class="card-modal-details">` | 320px scrollable right panel with card metadata. |
| Want button (in modal) | `modal-want-btn` | `<button class="want-btn">` | Toggles card on/off wishlist. Shows "Want" or "Wanted" with green styling when active. |
| Add to Collection button | `modal-add-btn` | `<button class="add-collection-btn">` | Opens inline form to add another copy to collection. |
| **Add Collection Form** (inline, toggled) | `add-collection-form-container` | `<div>` | Contains date, price, source inputs and confirm button. |
| Add date input | `add-date` | `<input type="date">` | Defaults to today. |
| Add price input | `add-price` | `<input type="number">` | Purchase price. Step 0.01. |
| Add source input | `add-source` | `<input type="text">` | Source/origin label. |
| Add confirm button | `add-confirm-btn` | `<button>` | Submits `POST /api/collection` to add card copy. |
| **Per-Copy Sections** | `copies-container` | `<div>` | Dynamically loaded. One `copy-section` per physical copy. |
| Receive button (per copy) | (dynamic) `.receive-btn` | `<button>` | Marks an ordered copy as received. `POST /api/collection/:id/receive`. |
| Dispose select (per copy) | (dynamic) `.dispose-select` | `<select>` | Options: Sold, Traded, Gifted, Lost, Listed (if owned), Unlist (if listed). |
| Dispose price input | (dynamic) `.dispose-price` | `<input type="number">` | Sale price for disposition. |
| Dispose note input | (dynamic) `.dispose-note` | `<input type="text">` | Note for disposition. |
| Dispose button | (dynamic) `.dispose-btn` | `<button>` | Submits disposition via `POST /api/collection/:id/dispose`. |
| Delete copy button | (dynamic) `.delete-copy-btn` | `<button>` | Deletes individual copy. Confirms with dialog. `DELETE /api/collection/:id?confirm=true`. |
| Reprocess button | (dynamic) `.reprocess-btn` | `<button>` | Re-identifies card from original image. `POST /api/ingest2/reset`. Only shown for image-ingested cards. |
| Refinish button | (dynamic) `.refinish-btn` | `<button>` | Removes card to fix finish, re-enters ingest. `POST /api/ingest2/refinish`. Only shown for image-ingested cards. |
| Add to Deck dropdown (per copy) | (dynamic) `.copy-add-to-deck` | `<select>` | Assign unassigned copy to a deck. Includes "New Deck..." option. |
| Add to Binder dropdown (per copy) | (dynamic) `.copy-add-to-binder` | `<select>` | Assign unassigned copy to a binder. Includes "New Binder..." option. |
| Remove from Deck link | (dynamic) `.copy-remove-deck` | `<a>` | Removes copy from its current deck. |
| Remove from Binder link | (dynamic) `.copy-remove-binder` | `<a>` | Removes copy from its current binder. |
| Move to Deck dropdown | (dynamic) `.copy-move-to-deck` | `<select>` | Moves copy from binder to a deck. Includes "New Deck..." option. |
| Move to Binder dropdown | (dynamic) `.copy-move-to-binder` | `<select>` | Moves copy from deck to a binder. Includes "New Binder..." option. |
| **Price History Chart** | `price-chart-section` | `<div>` | Chart.js line chart. Hidden if no price data. |
| Price chart canvas | `price-chart-canvas` | `<canvas>` | 150px tall chart area. |
| Price range pills | `price-range-pills` | `<div>` | 5 time-range buttons: 1M (30d), 3M (90d), 6M (180d), 1Y (365d), ALL (0). Disabled if data range is shorter than period. |
| **Filterable elements** in modal | (various) `.filterable` | `<span>`, `<div>` | Card name, type, set, rarity, finish, treatment tags in modal are clickable. Clicking closes modal and applies that value as a filter. Uses `data-filter-type` and `data-filter-value` attributes. |

### 3.7 Wishlist Panel (`wishlist-panel`)

Slides in from the right. 320px wide.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Wishlist panel | `wishlist-panel` | `<div>` | Side panel with header, scrollable list, and footer actions. |
| Wishlist close button | `wishlist-close` | `<button class="modal-close">` | X button to close panel. |
| Wishlist backdrop | `wishlist-backdrop` | `<div>` | Semi-transparent overlay. Click to close. |
| Wishlist entry list | `wishlist-panel-list` | `<div>` | Scrollable list of wishlist entries. Each entry is clickable to open card modal. |
| Remove entry button | (dynamic) `.wl-remove` | `<button>` | X button per entry. `DELETE /api/wishlist/:id`. |
| Copy for CK | `wl-copy-ck` | `<button class="secondary">` | Copies wishlist as CK format text, opens Card Kingdom builder. |
| Copy for TCG | `wl-copy-tcg` | `<button class="secondary">` | Copies wishlist as TCG format text, opens TCGplayer mass entry. |
| Clear All | `wl-clear-all` | `<button class="secondary">` | Deletes all wishlist entries after confirmation dialog. Red styling. |

### 3.8 Assign to Deck Modal (`assign-deck-overlay`)

Full-screen overlay for bulk deck assignment.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Deck select | `assign-deck-select` | `<select>` | Dropdown of all decks plus "New Deck..." option. |
| Zone select | `assign-deck-zone` | `<select>` | Dropdown: Mainboard, Sideboard, Commander. |
| Add button | (inline) | `<button>` | Calls `assignSelectedToDeck()`. Submits `POST /api/decks/:id/cards`. |
| Cancel button | (inline) | `<button class="secondary">` | Hides the overlay. |

### 3.9 Assign to Binder Modal (`assign-binder-overlay`)

Full-screen overlay for bulk binder assignment.

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Binder select | `assign-binder-select` | `<select>` | Dropdown of all binders plus "New Binder..." option. |
| Add button | (inline) | `<button>` | Calls `assignSelectedToBinder()`. Submits `POST /api/binders/:id/cards`. |
| Cancel button | (inline) | `<button class="secondary">` | Hides the overlay. |

### 3.10 Table View Elements

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Collection table | (class) `.collection-table` | `<table>` | Full-width table with sortable column headers. |
| Column headers | `th[data-col]` | `<th>` | Clickable to sort. Shows sort arrow when active. Toggles asc/desc on repeated click. |
| Select-all checkbox | `.sel-all-cb` | `<input type="checkbox">` | In header row. Only visible in multi-select mode. |
| Per-row select checkbox | `.row-sel-cb` | `<input type="checkbox">` | Per-row. Only visible in multi-select mode. Supports shift-click for range selection. |
| Row click | `tr[data-idx]` | `<tr>` | Clicking a row opens the card detail modal. |
| Filterable cells | `.filterable` | Various spans | Card name, type, subtype, set code, rarity icon, mana cost, finish tags, date are clickable to apply as filters. |

### 3.11 Grid View Elements

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Sort bar | `grid-sort-bar` | `<div class="sort-bar">` | Row of sort buttons matching all column definitions. Active sort shown with arrow. |
| Sort buttons | `.sort-btn` | `<span>` | One per column (Qty, Card, Type, Cost, Set, #, Price, Cond., Added, CK Buy $, TCG $). Click to sort. |
| Virtual scroll grid | `vgrid` | `<div class="card-grid">` | Absolutely-positioned card tiles with virtual scrolling. Only renders visible rows + 3-row buffer. |
| Card tile | `.sheet-card` | `<div>` | Card image with rarity border gradient, foil shimmer effect, quantity badge, wanted badge, ordered indicator. Click opens modal. |
| Grid select checkbox | `.select-checkbox` | `<input type="checkbox">` | Per-tile. Only visible in multi-select mode. Positioned top-left of card image. |

### 3.12 Orders View Elements

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Order group header | `.order-group-header` | `<div>` | Shows seller name, order number, date, card count, and ordered count. |
| Edit order link | (inline) | `<a>` | Links to `/edit-order?id=:orderId`. |
| Receive All button | `.receive-all-btn` | `<button>` | Per-order-group. Receives all ordered cards in one API call. `POST /api/orders/:id/receive`. |
| Ordered banner | `ordered-banner` | `<div>` | Banner showing "N cards awaiting delivery" with "View Ordered" button. Shown in table/grid views when ordered cards exist. |
| View Ordered button | `view-ordered-btn` | `<button>` | Activates the ordered status filter. |

---

## 4. User Flows

### 4.1 Basic Browsing

1. Page loads, fetches settings, cached sets, wishlist, and collection data in parallel.
2. Collection renders in default table view, sorted by name ascending.
3. Status bar shows "N entries, N cards -- TCG $X.XX".
4. User scrolls through the table to browse cards.

### 4.2 Searching for a Card

1. User types in the search input (`search-input`).
2. After 300ms debounce, a server fetch is triggered with `?q=<query>`.
3. Results replace the current card list.
4. All active client-side filters are re-applied to the new results.

### 4.3 Filtering Collection

1. User clicks "Filters" button to open sidebar.
2. Sidebar slides in from left with backdrop.
3. User selects filter criteria (e.g., checks "Rare" rarity pill, selects a set from the set dropdown).
4. Each filter change instantly re-filters and re-renders the view client-side (no server fetch, except for search text and disposition statuses).
5. Status text updates to reflect filtered count and value.
6. User clicks "Close Filters" or backdrop to dismiss.

### 4.4 Switching View Modes

1. User clicks one of the three view toggle buttons in the header.
2. **Table view**: Renders sortable table with configurable columns, card thumbnails, inline tags.
3. **Grid view**: Renders card images in a virtual-scrolled grid. Sort bar appears above the grid. Column +/- controls become visible.
4. **Orders view**: Groups cards by purchase order with headers showing seller, order number, date. Each group has a grid of card images and a "Receive All" button.

### 4.5 Viewing Card Details

1. User clicks a card row (table) or card tile (grid).
2. Card detail modal opens with full-size card image on left, details panel on right.
3. Details show: card name, mana cost, type, set with Keyrune icon, collector number, rarity, quantity, condition, finish, treatment tags.
4. Price badges link to Scryfall and Card Kingdom.
5. "Full page" badge links to standalone card detail page.
6. Per-copy data loads async showing each physical copy with status, order info, lineage, deck/binder assignment.
7. Price history chart loads async if price data exists, with time-range pills (1M, 3M, 6M, 1Y, ALL).
8. User can click "Flip" button to see back face of double-faced cards.
9. User can close modal by clicking X, clicking backdrop, or pressing Escape.

### 4.6 Clicking Filterable Elements in Modal

1. User opens a card modal.
2. Card name, type, set, rarity, finish, treatment tags are clickable (`.filterable` class).
3. Clicking one closes the modal and applies that value as a filter in the sidebar.
4. E.g., clicking a set name adds that set to the set filter and re-renders.

### 4.7 Managing Per-Copy Data

1. User opens card modal for an owned card.
2. Copies section loads showing each physical copy.
3. For each copy, user can:
   - **Receive** an ordered copy (changes status from ordered to owned).
   - **Dispose** a copy (sell, trade, gift, lose, list) with optional price and note.
   - **Delete** a copy (permanent, with confirmation).
   - **Reprocess** an image-ingested copy (re-runs identification).
   - **Refinish** an image-ingested copy (removes to fix finish detection).
   - **Assign to deck/binder** via dropdown (or create new deck/binder inline).
   - **Remove from deck/binder** via inline link.
   - **Move between deck and binder** via dropdown.

### 4.8 Adding a Card to Collection from Modal

1. User opens card modal (works for both owned and unowned cards).
2. Clicks "Add" button (`modal-add-btn`).
3. Inline form appears with date (defaults to today), price, and source fields.
4. User fills in details and clicks "Confirm".
5. `POST /api/collection` creates the new entry.
6. If the card was on the wishlist, it is automatically fulfilled and removed.
7. Copies section refreshes, collection re-fetches.

### 4.9 Wishlist Management

1. User opens More menu and clicks "Wishlist (N)" to open the wishlist panel.
2. Wishlist panel slides in from the right showing all unfulfilled entries.
3. User can click an entry name to open that card's modal.
4. User can click X on an entry to remove it from the wishlist.
5. Footer actions: "Copy for CK" / "Copy for TCG" copy card lists to clipboard and open vendor sites.
6. "Clear All" removes all entries after confirmation.
7. Adding to wishlist: In card modal, click "Want" button. Or in multi-select mode, click "Want" in selection bar.

### 4.10 Multi-Select Operations

1. User opens More menu, clicks "Toggle Multi-Select".
2. Selection bar appears below header. Checkboxes appear on each card (table rows or grid tiles).
3. User checks individual cards or uses shift-click for range selection.
4. "All" / "None" links in selection bar for bulk select/deselect.
5. Available bulk actions:
   - **Want**: Adds all selected to wishlist via `POST /api/wishlist/bulk`.
   - **Share**: Generates Scryfall search URL, shortens via `/api/shorten`, shows link.
   - **Add to Deck**: Opens deck assignment modal with deck and zone selects.
   - **Add to Binder**: Opens binder assignment modal.
   - **Delete**: Deletes all copies of selected cards after confirmation.
6. Toggling multi-select off clears all selections.

### 4.11 Include Unowned Mode (Set Completion)

1. User applies at least one filter (typically a set filter).
2. Opens More menu, clicks "+ Unowned" (now enabled because filters are active).
3. First click: `include_unowned=base` -- shows base printings of cards not in collection (greyed out).
4. Second click: `include_unowned=full` -- shows all printings including treatments.
5. Third click: disables include-unowned.
6. "Buy Missing" buttons appear in More menu (Copy for Card Kingdom, Copy for TCGplayer).
7. Status text changes to show "N owned, N missing (base/full) -- TCG $X.XX".
8. Unowned cards shown greyed out with reduced opacity. Wanted unowned cards shown slightly more visible.

### 4.12 Buy Missing Cards

1. User enables include-unowned mode with a set filter.
2. Opens More menu, clicks "Copy for Card Kingdom" or "Copy for TCGplayer".
3. Card list text is copied to clipboard in vendor format.
4. Vendor website opens in new tab.
5. If multi-select is active with selections, only selected unowned cards are included.

### 4.13 Sorting

1. **Table view**: Click any column header to sort by that column. Click again to reverse direction. Arrow indicator shows current sort state.
2. **Grid view**: Click any button in the sort bar above the grid. Same toggle behavior.
3. Sort is applied client-side. Secondary sort is always by card name.

### 4.14 Configuring Table Columns

1. In table view, click the grid icon in the leftmost table header cell.
2. Column configuration drawer slides in from the right.
3. Check/uncheck columns to show/hide them.
4. Changes are saved to `localStorage` key `collectionCols`.
5. Table re-renders immediately on each toggle.

### 4.15 Adjusting Grid Size

1. In grid view, the column count +/- control appears in the header.
2. Click "-" to reduce columns (min 1), "+" to increase (max 12).
3. Current count shown between buttons.
4. Grid re-renders with new column count. Saved to `localStorage` key `collectionGridCols`.

### 4.16 Changing Image Display Mode

1. Open More menu.
2. Under "Image Display", click "Crop" or "Contain" pill.
3. Crop mode (default): card thumbnails are cropped to fill their container.
4. Contain mode: card thumbnails are scaled to fit within their container, showing full card.
5. Setting persisted server-side via `PUT /api/settings`.

### 4.17 Setting Price Floor

1. Open More menu.
2. Under "Price Floor", enter a dollar amount.
3. Cards below this price are excluded from total value calculations in the status text.
4. Setting persisted server-side via `PUT /api/settings`.

### 4.18 Saving and Loading Views

1. Configure desired filters in the sidebar.
2. Click "Save Current Filters as View" at top of sidebar.
3. Enter a name in the prompt dialog.
4. View saved via `POST /api/views`.
5. To load: Select from the "Saved Views" dropdown at top of sidebar.
6. Selected view's filters are applied and collection re-fetches.

### 4.19 Receiving Ordered Cards

1. **Individual**: Open card modal for an ordered card. Click "Receive" button on the copy.
2. **Bulk per order**: In orders view, click "Receive All (N)" on an order group header.
3. **Via banner**: In table/grid view, an ordered-banner appears showing "N cards awaiting delivery". Click "View Ordered" to switch to ordered-only filter.

### 4.20 Container Filtering (Deck/Binder)

1. In the sidebar, use the "Container" dropdown.
2. Options: "All Cards", "Unassigned Only", or specific decks/binders (grouped with card counts).
3. Selecting a container filters the view to only cards in that deck or binder.

---

## 5. Dynamic Behavior

### 5.1 Initial Load Sequence

On page load, three parallel fetches fire:
1. `GET /api/settings` -- loads image_display, price_sources, price_floor settings.
2. `GET /api/cached-sets` -- loads all cached set codes/names for the set filter dropdown.
3. `GET /api/wishlist?fulfilled=false` -- loads unfulfilled wishlist entries.

After these complete:
4. `applySettings()` -- applies dynamic CSS and syncs UI controls.
5. `fetchCollection()` -- `GET /api/collection` -- loads all collection data.
6. `loadContainerData()` -- parallel fetches for `GET /api/decks`, `GET /api/binders`, `GET /api/views`.

### 5.2 Client-Side vs Server-Side Filtering

**Server-side** (triggers `GET /api/collection?...`):
- Search text (`q` parameter)
- Include unowned mode (`include_unowned` and `filter_set` parameters)
- Disposition status filters: sold, traded, gifted, lost (`status=all` parameter)

**Client-side** (instant refilter, no fetch):
- Color, rarity, type, subtype, finish, treatment/badge filters
- Set filter (except when include-unowned is active, which triggers server fetch)
- Collector number, mana value, price, date ranges
- Ordered and wanted status filters
- Container (deck/binder/unassigned) filter
- All sorting

### 5.3 Virtual Scrolling (Grid View)

The grid view uses virtual scrolling for performance with large collections:
- Calculates total grid height based on card count and column count.
- Only renders visible rows plus a 3-row buffer above and below.
- Uses `requestAnimationFrame`-throttled scroll listener.
- Cards are absolutely positioned within the grid container.
- Cleanup function removes scroll listener when switching away from grid view.

### 5.4 Debouncing

- Search input: 300ms debounce before server fetch.
- Range inputs (CN, CMC, price, date): 150ms debounce before client-side refilter.

### 5.5 Card Modal Lazy Loading

When a card modal opens:
1. Card image and basic details render immediately.
2. Per-copy data loads async via `GET /api/collection/copies?printing_id=X`.
3. Price history chart loads async via `GET /api/price-history/:set/:cn`.
4. Copy data includes deck/binder info loaded in parallel.

### 5.6 Ordered Banner

After every render, `renderOrderedBanner()` checks if any cards have `status === 'ordered'`. If so, a banner is inserted at the top of the main content area showing the count and a "View Ordered" button. This banner is removed if the user is already viewing the ordered-only filter.

### 5.7 Orders View Button Visibility

The orders view button in the header toggle group is shown/hidden dynamically based on whether any cards in the unfiltered dataset have ordered status. When all orders are received, the button hides and the view switches back to table.

### 5.8 Settings Persistence

Image display mode and price floor changes are persisted to the server via `PUT /api/settings`. Column configuration and grid column count are persisted to `localStorage`.

### 5.9 Include Unowned State Cycle

The include-unowned button cycles through three states on each click:
- `''` (off): Normal collection view.
- `'base'`: Server returns base printings of unowned cards from filtered sets.
- `'full'`: Server returns all printings (including special treatments) of unowned cards.

The button is disabled when no filters are active (checked via `hasAnyFilter()`). Clearing all filters resets include-unowned to off.

### 5.10 Filterable Element Click Propagation

Many text elements in both the table view and card modal have the class `filterable` with `data-filter-type` and `data-filter-value` attributes. Clicking these:
1. In table view: prevents row click (modal open), applies the filter.
2. In modal: closes the modal, applies the filter.

Filter types: `name`, `set`, `rarity`, `type`, `subtype`, `cmc`, `finish`, `badge`, `date_added`.

### 5.11 Wishlist Synchronization

Wishlist state is maintained in-memory with three maps: `wishlistMap` (by id), `wishlistByPrinting` (by printing_id), `wishlistByOracle` (by oracle_id). Any modification (add/remove from modal, bulk add, clear all) updates all three maps, updates the wishlist count in the More menu, and re-renders the wishlist panel.

### 5.12 Selection State

Multi-select state is tracked via a `Set` of indices into the `allCards` array. Shift-click enables range selection from the last selected index. Selection state is cleared on: toggling multi-select off, fetching new collection data, or clearing selection.

---

## 6. Data Dependencies

### 6.1 API Endpoints Called

| Endpoint | Method | When Called | Purpose |
|----------|--------|------------|---------|
| `/api/settings` | GET | Page load | Load image_display, price_sources, price_floor |
| `/api/settings` | PUT | Image display or price floor change | Persist settings |
| `/api/cached-sets` | GET | Page load | Load all cached set codes/names for set filter |
| `/api/wishlist?fulfilled=false` | GET | Page load | Load unfulfilled wishlist entries |
| `/api/collection` | GET | Page load, search, filter changes | Load collection data. Params: `q`, `include_unowned`, `filter_set`, `status` |
| `/api/decks` | GET | Page load (via `loadContainerData`) | Load all decks for container filter and assignment |
| `/api/binders` | GET | Page load (via `loadContainerData`) | Load all binders for container filter and assignment |
| `/api/views` | GET | Page load (via `loadContainerData`) | Load saved view configurations |
| `/api/views/:id` | GET | Loading a saved view | Fetch specific view's filter JSON |
| `/api/views` | POST | Saving a new view | Create named filter configuration |
| `/api/collection/copies` | GET | Card modal open, delete operation | Fetch per-copy details for a printing |
| `/api/price-history/:set/:cn` | GET | Card modal open | Fetch price time series for chart |
| `/api/collection/:id/receive` | POST | Receive button click | Mark ordered copy as received |
| `/api/collection/:id/dispose` | POST | Dispose button click | Change copy status (sold/traded/etc.) |
| `/api/collection/:id` | DELETE | Delete copy button click | Delete individual collection entry |
| `/api/collection` | POST | Add button in modal | Add new collection entry |
| `/api/collection/bulk-delete` | POST | Multi-select delete | Delete multiple collection entries |
| `/api/wishlist` | POST | Want button in modal | Add card to wishlist |
| `/api/wishlist/:id` | DELETE | Unwant button or remove from panel | Remove card from wishlist |
| `/api/wishlist/bulk` | POST | Multi-select want | Add multiple cards to wishlist |
| `/api/shorten` | GET | Share button | Shorten Scryfall URL |
| `/api/card/:printingId` | GET | Wishlist panel entry click (card not in view) | Fetch card data by printing ID |
| `/api/orders/:id/receive` | POST | Receive All button | Receive all cards in an order |
| `/api/decks/:id/cards` | POST | Deck assignment | Add cards to a deck |
| `/api/decks/:id/cards` | DELETE | Remove from deck | Remove cards from a deck |
| `/api/decks/:id/cards/move` | POST | Move to deck (from binder) | Move cards to a deck |
| `/api/binders/:id/cards` | POST | Binder assignment | Add cards to a binder |
| `/api/binders/:id/cards` | DELETE | Remove from binder | Remove cards from a binder |
| `/api/binders/:id/cards/move` | POST | Move to binder (from deck) | Move cards to a binder |
| `/api/decks` | POST | "New Deck..." option | Create a new deck |
| `/api/binders` | POST | "New Binder..." option | Create a new binder |
| `/api/ingest2/reset` | POST | Reprocess button | Re-identify image-ingested card |
| `/api/ingest2/refinish` | POST | Refinish button | Remove card to fix finish |

### 6.2 Required Data for Page to Function

- **Minimum**: The page needs `GET /api/collection` to return at least an empty array. Settings and cached sets are needed for full functionality.
- **For collection display**: At least one card in the collection with fields: `name`, `set_code`, `collector_number`, `printing_id`, `image_uri`, `type_line`, `mana_cost`, `rarity`, `colors`, `cmc`, `qty`, `finish`, `status`.
- **For set filter dropdown**: `GET /api/cached-sets` must return set data, or the collection data itself provides sets.
- **For price data**: Price fields (`tcg_price`, `ck_price`) must be populated in collection data. Price history requires the prices table to have time-series data.
- **For container filter**: Decks and binders must exist via `GET /api/decks` and `GET /api/binders`.
- **For saved views**: Views must exist via `GET /api/views`.

### 6.3 External Dependencies

- **Scryfall CDN**: Card images loaded from `card.image_uri` (Scryfall image URLs).
- **Chart.js v4**: Price history chart rendering.
- **chartjs-adapter-date-fns v3**: Date axis for price chart.
- **Keyrune CSS**: Set icons (loaded from CDN).
- **Mana Font CSS**: Mana cost icons (loaded from CDN).

---

## 7. Visual States

### 7.1 Page-Level States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Loading** | Initial fetch in progress | Main area shows "Loading collection..." in italic grey text. |
| **Empty collection** | API returns empty array, no filters active | Main area shows "No cards found" empty state. |
| **No filter results** | Filters active but no cards match | "No cards found" (table/grid) or "No ordered cards found" (orders view). |
| **Populated** | Cards loaded and displayed | Table rows, grid tiles, or order groups visible. |
| **Error** | API fetch fails | No explicit error state -- page stays in loading or previous state. |

### 7.2 View Mode States

| State | Visual |
|-------|--------|
| **Table view** | Full-width table with configurable columns, card thumbnails, sortable headers, inline tags. Column config icon visible. |
| **Grid view** | Card images in responsive grid with virtual scrolling. Sort bar above grid. Column size controls visible in header. |
| **Orders view** | Cards grouped by purchase order with group headers, receive-all buttons, and card grids per group. |

### 7.3 Card Visual States

| State | Table Appearance | Grid Appearance |
|-------|-----------------|-----------------|
| **Owned (normal)** | Full opacity row | Full color card image with rarity border gradient |
| **Owned (foil/etched)** | "F" or "E" inline tag | Rainbow shimmer overlay + animated foil streak |
| **Owned (qty > 1)** | Qty column shows count | Red qty badge (e.g., "3x") top-right |
| **Ordered** | 70% opacity, orange left border, "ORD" tag | 80% brightness, orange dot bottom-left |
| **Unowned** | 45% opacity | Grayscale 85%, brightness 55%, 60% opacity. No foil effects. |
| **Unowned + Wanted** | 70% opacity, "W" green tag | Grayscale 30%, brightness 75%, 85% opacity. Green "Want" badge top-left. |
| **Selected (multi-select)** | Red-tinted background row | Checkbox checked |
| **Treatment badges** | Inline tags: BL, SC, EA, FA, P, F, E | Overlay badges: BL, SC, EA, FA, Foil, Etched |

### 7.4 Sidebar States

| State | Appearance |
|-------|------------|
| **Closed** | Sidebar off-screen (left: -320px). No backdrop. |
| **Open** | Sidebar visible (left: 0). Semi-transparent backdrop visible. "Filters" button has active styling. |

### 7.5 Modal States

| State | Appearance |
|-------|------------|
| **Closed** | Overlay hidden (display: none). |
| **Open** | Full-screen dark overlay. Modal card with image left, details right. |
| **Flipped** | Card image rotated 180 degrees on Y axis showing back face. Details update for back face of DFC. |
| **Price chart visible** | Chart section shown below modal details. |
| **Price chart hidden** | No price data available -- section hidden. |
| **Copies loading** | "Loading copies..." text in copies area. |
| **Copies loaded** | Per-copy sections with controls. |
| **Add form open** | Inline form visible below "Add" button. |
| **Add form closed** | No form visible. |

### 7.6 Wishlist Panel States

| State | Appearance |
|-------|------------|
| **Closed** | Panel off-screen (right: -340px). |
| **Open, empty** | "Wishlist is empty" italic text. Footer buttons visible but non-functional. |
| **Open, populated** | Scrollable list of card names with set codes and remove buttons. |

### 7.7 Selection Bar States

| State | Appearance |
|-------|------------|
| **Multi-select off** | Selection bar hidden (display: none). |
| **Multi-select on, none selected** | Bar visible showing "0 selected". |
| **Multi-select on, some selected** | Bar shows "N selected" with All/None links and action buttons. |

### 7.8 Include Unowned States

| State | Button Text | Button Style | Status Text |
|-------|-------------|-------------|-------------|
| **Off (no filters)** | "+ Unowned" | Disabled, 35% opacity | "N entries, N cards -- TCG $X.XX" |
| **Off (filters active)** | "+ Unowned" | Enabled, normal | "N entries, N cards -- TCG $X.XX" |
| **Base mode** | "+ Unowned" | Active (blue background, red border) | "N owned, N missing (base) -- TCG $X.XX" |
| **Full mode** | "+ Full Set" | Active | "N owned, N missing (full) -- TCG $X.XX" |

### 7.9 More Menu States

| State | Appearance |
|-------|------------|
| **Closed** | Dropdown hidden. |
| **Open** | Dropdown visible below the ellipsis button. Contains all menu items. |
| **Buy Missing visible** | Two additional buttons shown when include-unowned is active. |
| **Buy Missing hidden** | Buttons hidden when include-unowned is off. |

### 7.10 Ordered Banner State

| State | Appearance |
|-------|------------|
| **No ordered cards** | No banner shown. |
| **Ordered cards exist (not in ordered filter)** | Orange-tinted banner at top of content: "N cards awaiting delivery" with "View Ordered" button. |
| **Already viewing ordered filter** | Banner not shown (user is already seeing ordered cards). |
