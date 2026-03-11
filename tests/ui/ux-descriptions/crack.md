# Crack-a-Pack Page UX Description

Source: `/home/ryangantt/workspace/efj-mtgc/mtg_collector/static/crack_pack.html`
Route: `/crack`

---

## 1. Page Purpose

The Crack-a-Pack page is a virtual booster pack simulator for Magic: The Gathering. Users select a set and product type (e.g., draft booster, collector booster), then generate a randomized pack of cards based on actual set sheet data. Cards can be opened in "surprise" mode (face-down, revealed one at a time) or all-at-once mode. Users can pick favorite cards from the pack into a persistent picks list stored in localStorage, view card prices from Scryfall (TCGplayer) and Card Kingdom, zoom into card images, adjust the grid layout, and share/restore specific pack states via URL hash. The page also links to an "Explore Sheets" page for the selected set/product.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| Header title "Crack-a-Pack" | `<a>` wrapping `<h1>` | `/` (homepage) | Styled with `color:inherit; text-decoration:none` so it looks like plain text |
| "Explore Sheets" button | `<button>` id=`sheets-btn` | `/sheets#set=X&product=Y` | Navigates to the sheets page with the currently selected set and product encoded in the URL hash. Disabled until a set with products is selected. |
| Scryfall card links (SF badge) | `<a>` with class `badge link` | `https://scryfall.com/card/{set}/{cn}` | Opens in new tab (`target="_blank"`). Appears on each card and in the picks panel. |
| Card Kingdom card links (CK badge) | `<a>` with class `badge link` | Card Kingdom product URL from `card.ck_url` | Opens in new tab (`target="_blank"`). Appears on each card and in the picks panel. Only shown if CK data is available. |

---

## 3. Interactive Elements

### Header Controls

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Set search input | `set-input` | `<input type="text">` | Searchable text input for finding MTG sets. Starts disabled with placeholder "Loading sets..." until the `/api/sets` call completes, then changes to "Search sets...". On focus, clears any previously selected set and opens the dropdown. Filters sets by name or code as user types. Supports keyboard navigation (ArrowUp, ArrowDown, Enter, Escape). |
| Set dropdown | `set-dropdown` | `<ul>` | Absolutely-positioned dropdown list below the set input. Hidden by default; shown (class `open`) on input focus or typing. Each `<li>` displays `{set name} ({set code})` and has `data-code` attribute. Max height 300px with scroll. Items highlight on hover or keyboard selection (class `active`). Closes on blur or Escape. |
| Product radio buttons | `product-radios` | `<div>` containing dynamically generated `<input type="radio">` elements | Container for product type selection. Populated after a set is selected via `/api/products?set=X`. Each product gets a radio input with `name="product"`, `id="product-{name}"`, and a `<label>`. The radio inputs are visually hidden; the labels are styled as pill-shaped toggle buttons (border-radius: 20px). First product is auto-selected. Selected state uses red (#e94560) background. |
| Open Pack button | `open-btn` | `<button>` | Primary action button. Disabled until a set and product are selected. Triggers `openPack()` which POSTs to `/api/generate`. Temporarily disabled during pack generation. |
| Surprise mode toggle | `open-mode` | `<input type="checkbox">` | Checkbox (visually hidden, styled as pill toggle via label). Checked by default. When checked, newly opened packs show cards face-down. When unchecked, cards are revealed immediately. Label text: "Surprise". |
| Reveal All button | `reveal-all-btn` | `<button>` | Flips all face-down cards face-up at once. Disabled when no face-down cards exist or no pack is open. Becomes enabled after opening a pack in surprise mode. |
| Explore Sheets button | `sheets-btn` | `<button>` | Navigates to `/sheets` with current set/product in hash. Styled differently (gray background `#333`, gray border `#555`). Disabled until a set with products is loaded. |
| Column minus button | `col-minus` | `<button>` with class `col-btn` | Decreases the pack grid column count by 1. Minimum 1 column. Disabled at minimum. |
| Column count display | `col-count` | `<div>` | Non-interactive display showing current column count. Sits between the minus and plus buttons. |
| Column plus button | `col-plus` | `<button>` with class `col-btn` | Increases the pack grid column count by 1. Maximum 12 columns. Disabled at maximum. |
| CK prices status | `prices-status` | `<span>` with class `prices-status` | Clickable text showing CardKingdom price data age (e.g., "CK: 2h ago", "CK: not loaded", "CK: unavailable"). Clicking triggers a POST to `/api/fetch-prices` to download fresh price data. Shows "CK: downloading..." with red text (class `loading`) during download. Title attribute: "Click to update CK prices". |
| Status text | `status-text` | `<span>` | Read-only status display. Shows "Loading sets...", "{N} sets loaded", "Generating pack...", or empty. |

### Pack Grid Area

| Element | ID / Selector | Type | Description |
|---------|---------------|------|-------------|
| Pack header | `pack-header` | `<h2>` | Displays pack metadata after generation: "{set_code} {product} -- {N} cards (variant {index}, {pct}%) -- ${total}". Default text: "Select a set and open a pack". |
| Pack grid | `pack-grid` | `<div>` with class `pack-grid` | CSS Grid container for card slots. Column count controlled by `--grid-cols` CSS variable (default 5, or 3 on screens < 600px). |
| Card slots | `.card-slot` (dynamically created) | `<div>` | Each card in the pack. Has `data-printing-id` and `data-index` attributes. Click behavior depends on state: if face-down (class `face-down`), click flips the card face-up with a 0.5s CSS rotateY(180deg) transition; if face-up, click toggles the card as a "pick". Picked cards get class `picked` which adds a red glow border and a "PICKED" badge overlay (top-right). Each slot contains a `.card-img-wrap` with front/back faces, and a `.card-info` bar with badges. |
| Card image wrapper | `.card-img-wrap` | `<div>` | Contains front and back faces for the flip animation. Uses CSS 3D transforms (`perspective: 800px`, `transform-style: preserve-3d`). Has `--rarity-color` and `--set-color` CSS variables controlling the gradient border. Aspect ratio: 488/680. |
| Card front | `.card-front` | `<div>` | Shows the card image. Gets class `foil` for foil cards, which adds a rainbow wash overlay (repeating-linear-gradient with `mix-blend-mode: color`) and an animated light streak (3s ease-in-out infinite `foil-streak` animation). |
| Card back | `.card-back` | `<div>` | Shows `/static/card_back.jpeg`. Visible when card is face-down via `backface-visibility` and `rotateY(180deg)`. |
| Zoom badge | `.badge.zoom-badge` (per card) | `<span>` | Magnifying glass icon on each card's info bar. Clicking opens the zoom overlay with that card's image. Does nothing if the card is face-down (click is ignored). Uses `event.stopPropagation()` to prevent toggling the pick. |
| SF badge | `a.badge.link` | `<a>` | Scryfall link with optional TCGplayer price (e.g., "SF $1.50"). Opens in new tab. Shown per card based on `price_sources` setting. Uses `event.stopPropagation()` to prevent toggling the pick. |
| CK badge | `a.badge.link` | `<a>` | Card Kingdom link with optional CK price (e.g., "CK $2.00"). Opens in new tab. Only shown if `card.ck_url` exists and `ck` is in `price_sources` setting. Uses `event.stopPropagation()` to prevent toggling the pick. |
| Treatment badges | `.badge.treatment` | `<span>` | Shown per card for special treatments: BL (borderless), SC (showcase), EA (extended art), FA (full art). Teal-colored with gradient background. |

### Zoom Overlay

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Zoom overlay | `zoom-overlay` | `<div>` | Full-screen fixed overlay with semi-transparent black background (rgba(0,0,0,0.75)). Hidden by default; shown (class `active`) when a zoom badge is clicked. Clicking anywhere on the overlay closes it. |
| Zoom image | `zoom-img` | `<img>` | Large card image displayed centered in the overlay. Max height 85vh, max width 90vw. Rounded corners (16px) with heavy box shadow. |

### Picks Panel (Right Sidebar)

| Element | ID / Selector | Type | Description |
|---------|---------------|------|-------------|
| Picks heading | n/a | `<h2>` | Static text "Picks" with pick count span. |
| Pick count | `pick-count` | `<span>` | Shows "(N)" where N is the number of picked cards. Updates dynamically. |
| Clear All button | `clear-picks` | `<button>` | Clears all picks from the list and localStorage. Styled with gray background that turns red on hover. |
| Pick list | `pick-list` | `<ul>` with class `pick-list` | Vertical list of picked cards. Shows empty state message "Click cards to pick them" when no picks exist. |
| Pick items | `.pick-item` (dynamically created) | `<li>` | Each picked card displays: thumbnail image (40px wide), card name, set code + collector number, price/treatment badges, and a remove button (x). Has a left-edge color stripe using `--rarity-color`/`--set-color` gradient. Clickable (cursor: pointer). |
| Remove pick button | `.remove-pick` | `<span>` | "x" character on each pick item. Clicking removes that card from picks. Uses `event.stopPropagation()`. Turns red on hover. |

---

## 4. User Flows

### Flow 1: Select a Set

1. Page loads; set input shows "Loading sets..." and is disabled.
2. `/api/sets` completes; input is enabled with placeholder "Search sets...".
3. User clicks the set input field.
4. If a set was previously selected, the input clears and the full set list appears in the dropdown.
5. User types a partial set name or code (e.g., "midnight" or "mid").
6. Dropdown filters to matching sets in real-time.
7. User selects a set by clicking a dropdown item, or by using ArrowUp/ArrowDown and pressing Enter.
8. Input shows "{set name} ({set code})" and the dropdown closes.
9. `/api/products?set=X` is fetched; product radio buttons appear.
10. First product is auto-selected; "Open Pack" and "Explore Sheets" buttons become enabled.

### Flow 2: Change Product Type

1. After a set is selected, product radio buttons are visible (e.g., "draft", "collector", "play").
2. User clicks a different product label/pill.
3. The corresponding radio button is checked and highlighted red.
4. The next "Open Pack" will use this product type.

### Flow 3: Open a Pack (Normal Mode)

1. User unchecks "Surprise" toggle (or it was already unchecked).
2. User clicks "Open Pack".
3. Button disables; status shows "Generating pack...".
4. POST to `/api/generate` with `{set_code, product}`.
5. Pack header updates with set code, product, card count, variant info, and total price.
6. Cards render face-up in the grid. Each card shows its image, zoom badge, price badges, and treatment badges.
7. URL hash updates with set, product, seed, surprise=0, and all card indices as revealed.
8. "Reveal All" button is disabled (no face-down cards).
9. "Open Pack" button re-enables.

### Flow 4: Open a Pack (Surprise Mode)

1. User ensures "Surprise" toggle is checked (default state).
2. User clicks "Open Pack".
3. Same API call as normal mode.
4. All cards render face-down showing card back images.
5. "Reveal All" button becomes enabled.
6. URL hash updates with surprise=1 and empty revealed list.

### Flow 5: Reveal Individual Cards

1. Pack is open in surprise mode; cards are face-down.
2. User clicks a face-down card.
3. Card flips face-up with a 0.5s 3D rotation animation.
4. URL hash updates to include this card's index in the revealed list.
5. "Reveal All" button remains enabled if other cards are still face-down.
6. Clicking a face-up card toggles its pick state instead.

### Flow 6: Reveal All Cards

1. Pack is open in surprise mode with some or all cards face-down.
2. User clicks "Reveal All" button.
3. All remaining face-down cards flip face-up simultaneously.
4. "Reveal All" button becomes disabled.
5. URL hash updates with all indices in the revealed list.

### Flow 7: Pick a Card

1. A face-up card is visible in the pack grid.
2. User clicks the card image area (not a badge link).
3. Card gets a red glow border and a "PICKED" overlay badge (top-right corner).
4. Card appears in the picks panel on the right with thumbnail, name, set/CN, and price/treatment badges.
5. Pick count updates (e.g., "(1)").
6. Picks are saved to localStorage under key `crackPackPicks`.

### Flow 8: Unpick a Card

1. A picked card is in the pack grid (showing red glow and "PICKED" badge).
2. User clicks the card again.
3. "PICKED" overlay and red glow are removed.
4. Card is removed from the picks panel.
5. Pick count decreases.
6. localStorage is updated.

### Flow 9: Remove a Pick from the Panel

1. User sees a card in the picks panel.
2. User clicks the "x" button on the right side of a pick item.
3. Card is removed from picks.
4. If the card's pack is still displayed, the "PICKED" styling is removed from the grid card.
5. Pick count updates.

### Flow 10: Clear All Picks

1. User clicks "Clear All" button in the picks panel.
2. All picks are removed.
3. Picks panel shows empty state: "Click cards to pick them".
4. Pick count shows "(0)".
5. All "PICKED" overlays are removed from the pack grid.
6. localStorage is cleared of picks.

### Flow 11: Zoom Into a Card

1. A face-up card is displayed in the pack grid.
2. User clicks the magnifying glass zoom badge below the card.
3. Full-screen overlay appears with the card image at large size (up to 85vh x 90vw).
4. User clicks anywhere on the overlay to close it.

### Flow 12: Adjust Grid Column Count

1. User clicks the "-" button to decrease columns or "+" to increase.
2. Grid immediately re-layouts with the new column count.
3. Column count display updates.
4. Value is saved to localStorage under key `crackPackGridCols`.
5. Buttons disable at min (1) or max (12).

### Flow 13: Update Card Kingdom Prices

1. Prices status shows current state (e.g., "CK: 2h ago" or "CK: not loaded").
2. User clicks the prices status text.
3. Text changes to "CK: downloading..." with red color.
4. POST to `/api/fetch-prices` is sent.
5. On success, text updates to "CK: just now" (or similar time-ago format).
6. On error, text shows "CK: error".

### Flow 14: Share/Restore a Pack via URL Hash

1. After opening a pack, the URL hash is automatically set to encode: set code, product, seed, surprise mode, and which card indices are revealed.
   - Format: `#set=X&product=Y&seed=Z&surprise=0|1&revealed=0,1,2,...`
2. User copies the URL and shares it (or bookmarks it).
3. When someone opens the URL:
   a. Page loads sets from `/api/sets`.
   b. Hash is parsed; the matching set is found and selected.
   c. Surprise mode checkbox is set from the hash.
   d. Products are loaded for that set; the correct product is selected.
   e. `openPack(seed, revealed)` is called with the saved seed and revealed indices.
   f. The exact same pack is regenerated (deterministic via seed).
   g. Cards are shown face-up or face-down based on the `revealed` list from the hash.

### Flow 15: Navigate to Explore Sheets

1. User has a set and product selected.
2. User clicks "Explore Sheets" button.
3. Browser navigates to `/sheets#set=X&product=Y`.

### Flow 16: Open Multiple Packs Sequentially

1. User has already opened a pack.
2. User clicks "Open Pack" again (same or different set/product).
3. Previous pack grid is replaced with the new pack.
4. Existing picks from prior packs remain in the picks panel (picks persist across packs in localStorage).
5. Pick state is synced -- picks from the prior pack no longer highlight in the new grid (different printing IDs and indices).

---

## 5. Dynamic Behavior

### On Page Load
- `renderPicks()` is called to restore picks from localStorage.
- `loadPricesStatus()` fetches `/api/prices-status` and updates the CK status text.
- `fetch('/api/settings')` loads app settings (used for `price_sources` to determine which price badges to show).
- `loadSets()` fetches `/api/sets`, populates `allSets`, enables the set input, and updates status text.
- After sets load, `parseHash()` checks for URL hash parameters. If present, it auto-selects the set, loads products, selects the product, and opens the pack with the stored seed and revealed state.

### Set Search Dropdown
- Typing in the set input filters `allSets` by name or code (case-insensitive substring match).
- The dropdown renders the filtered list dynamically.
- Keyboard navigation (ArrowUp/ArrowDown) scrolls the active item into view.
- On focus, if a set was previously selected, the input clears to allow re-searching.
- On blur, the dropdown hides.

### Product Radio Buttons
- Dynamically generated after set selection. Each product from `/api/products` gets a radio input + label.
- First product is auto-checked. The native radio inputs are hidden; labels are styled as pill toggles.

### Card Flip Animation
- Cards use CSS 3D transforms. Face-down cards have `transform: rotateY(180deg)` on the `.card-img-wrap`, showing the card back (which itself has `rotateY(180deg)` to appear correctly). Removing the `face-down` class triggers a 0.5s transition back to `rotateY(0)`, revealing the front face.

### Foil Animation
- Foil cards (where `card.foil === true`) get class `foil` on `.card-front`.
- Two pseudo-elements provide the effect:
  - `::before`: static rainbow wash overlay using `repeating-linear-gradient` at 135deg with `mix-blend-mode: color`.
  - `::after`: animated light streak using `linear-gradient` with `background-position` animation (`foil-streak` keyframes, 3s ease-in-out infinite). The streak moves from bottom-right to top-left.
- Both pseudo-elements are hidden when the card is face-down.

### Rarity/Set Border Colors
- Each card's `.card-img-wrap` has a gradient border from `--rarity-color` (top) to `--set-color` (bottom).
- Rarity colors: common=#111, uncommon=#6a6a6a, rare=#c9a816 (gold), mythic=#d4422a (red).
- Set color: if the card's set code differs from the pack's set code (bonus sheet / guest card), the bottom gradient is purple (#5c2d91); otherwise #111.

### Pick State Synchronization
- `syncPickState()` iterates all `.card-slot` elements, checks if their `data-printing-id` + `data-index` matches any entry in the `picks` array, and toggles the `picked` class accordingly.
- Called after every pick toggle, pick removal, clear, and pack render.

### URL Hash State
- Updated after every pack open, card reveal, and reveal-all action.
- Encodes: `set`, `product`, `seed` (integer), `surprise` (0 or 1), `revealed` (comma-separated card indices that are face-up).
- On page load, if the hash contains valid params, the pack is deterministically reconstructed.

### Pack Header Statistics
- After pack generation, the header shows: set code, product name, card count, variant index, variant weight as a percentage of total weight, and total pack value (sum of TCG or CK prices based on `price_sources` setting).
- Format: `"{setCode} {product} -- {N} cards (variant {variantIndex}, {pct}%) -- ${total}"`

### Picks Panel Persistence
- Picks are stored in `localStorage` under key `crackPackPicks` as a JSON array.
- Each pick entry includes full card data plus `_packIndex` (position in pack) and `_packSetCode` (pack's set code, used for set-color border).
- Picks persist across page reloads and across different pack opens.

### Grid Column Persistence
- Column count stored in `localStorage` under key `crackPackGridCols`.
- Default: 5 on desktop, 3 on screens < 600px wide.

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When Called | Request | Response | Required Data |
|----------|--------|------------|---------|----------|---------------|
| `/api/sets` | GET | Page load | None | JSON array of `{name, code}` objects | Sets must be cached in the DB (via `mtg setup` / `mtg cache all`) |
| `/api/products?set={code}` | GET | After set selection | Query param: `set` (set code) | JSON array of product name strings (e.g., `["draft", "collector", "play"]`) | Set must have sheet/product data loaded (from MTGJSON) |
| `/api/generate` | POST | On "Open Pack" click | `{set_code, product, seed?}` | `{cards: [...], seed, set_code, variant_index, variant_weight, total_weight}` | Set must have sheet data; card printings with images must exist |
| `/api/prices-status` | GET | Page load | None | `{available: bool, last_modified: iso_string}` | None (returns status even if no prices) |
| `/api/fetch-prices` | POST | On CK status click | None | `{last_modified: iso_string}` or `{error: string}` | Network access to Card Kingdom price source |
| `/api/settings` | GET | Page load | None | JSON object with settings (e.g., `{price_sources: "tcg,ck"}`) | Settings table in DB |

### Card Data Fields Used

Each card object in the generate response must include:
- `printing_id` -- unique ID for pick tracking
- `name` -- card name displayed in picks panel
- `set_code` -- used for Scryfall links, set-color borders, pick display
- `collector_number` -- used for Scryfall links, pick display
- `rarity` -- used for border color (common/uncommon/rare/mythic)
- `image_uri` -- Scryfall CDN URL for card image
- `foil` -- boolean, triggers foil visual effects
- `border_color` -- "borderless" triggers BL badge
- `frame_effects` -- JSON array, checked for "showcase" (SC badge) and "extendedart" (EA badge)
- `is_full_art` -- boolean, triggers FA badge
- `tcg_price` -- TCGplayer price (optional)
- `ck_price` -- Card Kingdom price (optional)
- `ck_url` -- Card Kingdom product URL (optional, controls whether CK badge is shown)

### Static Assets
- `/static/favicon.ico` -- page favicon
- `/static/card_back.jpeg` -- card back image used for face-down cards
- Card images from Scryfall CDN (e.g., `https://cards.scryfall.io/...`) -- loaded via `card.image_uri`

---

## 7. Visual States

### Initial / Empty State
- Set input shows "Loading sets..." (disabled).
- Product radios area is empty.
- "Open Pack" button is disabled.
- "Reveal All" button is disabled.
- "Explore Sheets" button is disabled.
- Pack header shows: "Select a set and open a pack".
- Pack grid is empty.
- Picks panel shows "(0)" count and "Click cards to pick them" in italic gray text.
- CK status shows one of: "CK: {time} ago", "CK: not loaded", or "CK: unavailable".
- Status text shows "Loading sets...".

### Sets Loaded State
- Set input is enabled with placeholder "Search sets...".
- Status text shows "{N} sets loaded".
- All other elements remain in their initial state until a set is selected.

### Set Selected / Products Loading
- Set input shows "{set name} ({set code})".
- Product radios area shows "Loading..." text.
- "Open Pack" button remains disabled during product load.

### Set Selected / Products Loaded
- Product radio pills are visible; first is selected (red background).
- "Open Pack" button is enabled.
- "Explore Sheets" button is enabled.

### Pack Open -- Normal Mode (All Face-Up)
- Pack header shows pack metadata with variant and price info.
- Cards are displayed face-up in the grid, showing card images with rarity-colored gradient borders.
- Foil cards have rainbow wash and animated light streak effects.
- Each card has a zoom badge and price/treatment badges below it.
- "Reveal All" is disabled (no face-down cards).
- "Open Pack" button is re-enabled.

### Pack Open -- Surprise Mode (All Face-Down)
- Pack header shows pack metadata.
- All cards show the card back image.
- "Reveal All" button is enabled.
- Clicking individual cards flips them one at a time.

### Pack Open -- Partially Revealed
- Mix of face-up and face-down cards in the grid.
- "Reveal All" button is enabled.
- URL hash reflects which specific cards are revealed.

### Card Picked State
- The picked card in the grid has:
  - Red glow border: `box-shadow: 0 0 0 3px #e94560, 0 0 16px rgba(233,69,96,0.4)`
  - "PICKED" badge overlay in top-right corner (red background, white text, 0.7rem)
- The card appears in the picks panel sidebar with thumbnail, name, set/CN, badges, and remove button.

### Picks Panel -- With Picks
- Pick count shows "(N)" where N > 0.
- Pick items listed vertically, each with left-edge rarity/set color stripe.
- "Clear All" button is visible.

### Zoom Overlay Active
- Full-screen dark overlay covers the page.
- Large card image centered on screen.
- Cursor is pointer (click anywhere to close).

### CK Prices Loading State
- Prices status text shows "CK: downloading..." in red (#e94560) color.
- Element has class `loading`.

### CK Prices Error State
- Prices status text shows "CK: error" or "CK: unavailable".

### Dropdown Open State
- Set dropdown (`.set-dropdown.open`) is visible below the input.
- Filtered list of sets is shown.
- Active item (keyboard-navigated) has blue background (#0f3460).
- Max height 300px with vertical scrolling for long lists.

### Mobile / Responsive State (viewport <= 768px)
- Main layout switches from side-by-side (pack + picks panel) to vertical stack.
- Picks panel takes full width below the pack area.
- Picks panel gets a top border instead of left border.
- Grid defaults to 3 columns instead of 5.

### Hash-Restored State
- Identical to a normal pack-open state, but the specific seed, product, surprise mode, and revealed card indices are restored from the URL hash.
- Cards that were revealed when the URL was generated are face-up; others are face-down.
- The set input, product radio, and surprise toggle all reflect the hash state.
