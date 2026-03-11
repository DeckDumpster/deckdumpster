# Explore Sheets — UX Description

Source: `/home/ryangantt/workspace/efj-mtgc/mtg_collector/static/explore_sheets.html`
Route: `/sheets`

---

## 1. Page Purpose

The Explore Sheets page lets users browse the internal booster-pack composition ("sheets") for any MTG set and product type available in the local database. Users select a set and a product (e.g., "play", "collector"), and the page displays every sheet used to construct that booster: which cards appear on each sheet, their pull-rate weights, rarity groupings, price badges, and foil treatments. It also shows the variant table — the different possible booster configurations and their probabilities. The page serves as a reference tool for understanding exact pack odds and card distribution before opening virtual packs.

---

## 2. Navigation

| Element | Type | Target | Notes |
|---------|------|--------|-------|
| "Explore Sheets" (header h1) | `<a>` link | `/` (homepage) | Styled to match header color, no underline |
| "Open Pack" button | `<button>` | `/crack#set=...&product=...` | Navigates to the crack-a-pack page with current set/product pre-selected via hash |
| Scryfall badge per card | `<a>` link | `https://scryfall.com/card/{set}/{cn}` | Opens in new tab; labeled "SF" optionally with TCG price |
| Card Kingdom badge per card | `<a>` link | Card Kingdom URL from API | Opens in new tab; labeled "CK" optionally with CK price |

There is no shared site navigation bar. The only way back to the homepage is the "Explore Sheets" title link.

---

## 3. Interactive Elements

### Header Controls

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Set search input | `#set-input` | `<input type="text">` | Searchable text input for filtering and selecting a set. Starts disabled with placeholder "Loading sets...", becomes enabled with placeholder "Search sets..." after sets load. Width 260px. `autocomplete="off"`. |
| Set dropdown | `#set-dropdown` | `<ul>` | Dropdown list below the input. Hidden by default; shown (class `open`) on input focus or typing. Max height 300px, scrollable. Each `<li>` shows `"{Set Name} ({code})"`. Supports keyboard navigation (ArrowUp, ArrowDown, Enter, Escape). Mouse click on a `<li>` selects that set. |
| Product radio buttons | `#product-radios` | `<div>` container | Dynamically populated with `<input type="radio">` + `<label>` pairs after a set is selected. Each radio has `name="product"`, `id="product-{value}"`, `value="{product_name}"`. Styled as pill-shaped toggle buttons (border-radius 20px). The first product is auto-selected. Hidden radio inputs; labels serve as the visible control. |
| Open Pack button | `#pack-btn` | `<button>` | Disabled by default and when no product is selected. Has class `nav-secondary` (gray background). Navigates to `/crack#set=...&product=...`. |
| Column minus button | `#col-minus` | `<button>` | Decreases the card grid column count by 1. Disabled when grid columns reach minimum (1). Has class `col-btn`. Displays minus sign. |
| Column count display | `#col-count` | `<div>` | Shows current grid column count. Not interactive. |
| Column plus button | `#col-plus` | `<button>` | Increases the card grid column count by 1. Disabled when grid columns reach maximum (12). Has class `col-btn`. Displays plus sign. |
| Status text | `#status` | `<div>` | Read-only status area in the header, right-aligned (`margin-left: auto`). Shows loading progress and final stats like "8 sheets, 421 cards". |

### Content Area (Dynamically Generated)

| Element | Class/ID | Type | Description |
|---------|----------|------|-------------|
| Section header | `.section-header` | `<div>` (click target) | Clickable header for each collapsible section (Variants section + one per sheet). Toggling adds/removes class `open` on parent `.section`. Contains arrow indicator, title, and metadata. |
| Card image | `.sheet-card` | `<div>` (click target) | Each card in the grid is clickable. Clicking opens the zoom overlay with that card's full image. |
| Zoom overlay | `#zoom-overlay` | `<div>` | Full-viewport fixed overlay. Clicking anywhere on the overlay dismisses it (removes class `active`). |
| Zoom image | `#zoom-img` | `<img>` | The enlarged card image inside the zoom overlay. |
| Scryfall link badge | `a.badge.link` | `<a>` | Per-card external link to Scryfall. Shows "SF" + optional TCG price. Opens in new tab. |
| Card Kingdom link badge | `a.badge.link` | `<a>` | Per-card external link to Card Kingdom. Shows "CK" + optional CK price. Opens in new tab. |

---

## 4. User Flows

### Flow 1: Browse Sheets for a Set

1. Page loads. Set input is disabled showing "Loading sets...".
2. `/api/sets` and `/api/settings` are fetched simultaneously.
3. Input becomes enabled, placeholder changes to "Search sets...". Status shows "N sets loaded".
4. User clicks the set input. If a set was already selected, the input clears. The full set list appears in the dropdown.
5. User types to filter. Dropdown filters in real-time by set name or code (case-insensitive substring match).
6. User selects a set by clicking a dropdown item, or using ArrowDown/ArrowUp + Enter.
7. Input text updates to `"{Set Name} ({code})"`. Dropdown closes.
8. `/api/products?set={code}` is fetched. Product radio area shows "Loading...".
9. Product radio pills appear. The first product is auto-selected.
10. "Open Pack" button becomes enabled.
11. `/api/sheets?set={code}&product={product}` is fetched automatically. Content area shows "Loading sheets...".
12. URL hash updates to `#set={code}&product={product}`.
13. Sheets render: Variants section (open by default) + one collapsed section per sheet.

### Flow 2: Switch Product

1. User clicks a different product radio pill.
2. The pill highlights (red background). The `change` event fires.
3. URL hash updates. Sheets reload via `/api/sheets` with the new product.
4. Content area replaces with new sheet data.

### Flow 3: Explore Sheet Contents

1. User clicks a collapsed sheet section header.
2. Section expands (class `open` added), revealing card subgroups.
3. Cards are grouped by (set_code, rarity, weight). Each subgroup has a header showing rarity, group odds (fraction + percentage), and per-card odds.
4. Cards display as a grid of images with badges below each card.
5. User clicks a card image. The zoom overlay appears with a large version of the card.
6. User clicks anywhere on the overlay. The overlay dismisses.

### Flow 4: Adjust Grid Columns

1. User clicks the `+` button to add a column or the `-` button to remove one.
2. Grid column count updates immediately via CSS custom property `--grid-cols`.
3. The column count display updates to show the new number.
4. The preference is persisted to `localStorage` under key `exploreGridCols`.
5. Buttons disable at min (1) or max (12).

### Flow 5: Navigate to Pack Opening

1. User has a set and product selected.
2. User clicks the "Open Pack" button.
3. Browser navigates to `/crack#set={code}&product={product}`.

### Flow 6: Deep Link via URL Hash

1. User navigates to `/sheets#set=blb&product=play`.
2. Page loads, fetches sets.
3. After sets load, the hash is parsed. The matching set is auto-selected.
4. Products for that set are fetched. The hash-specified product is auto-selected.
5. Sheets load and render immediately without user interaction.

### Flow 7: Keyboard Navigation in Set Dropdown

1. User focuses the set input. Dropdown opens.
2. User presses ArrowDown repeatedly. Active highlight moves down the list, scrolling into view.
3. User presses ArrowUp. Active highlight moves up.
4. User presses Enter. The highlighted set is selected; dropdown closes; products load.
5. User presses Escape. Dropdown closes and input blurs.

---

## 5. Dynamic Behavior

### On Page Load

- `fetch('/api/settings')` is called. Result stored in `_settings` (used for price source configuration: which price badges to show).
- `loadSets()` is called: `fetch('/api/sets')` returns a JSON array of `{code, name}` objects. The input is enabled and all sets are stored in `allSets`.
- After sets load, the URL hash is parsed. If `set` and `product` params are found, the set is auto-selected, products are loaded, and the specified product is activated.

### On Set Selection

- `loadProducts(setCode)` calls `fetch('/api/products?set={code}')`. Returns a JSON array of product name strings.
- Radio buttons are dynamically created for each product. The first is auto-checked.
- `onSelectionChange()` fires, which calls `updateHash()` then `loadSheets()`.

### On Product Change or Selection Change

- `updateHash()` sets `location.hash` to `set={code}&product={product}`.
- `loadSheets()` calls `fetch('/api/sheets?set={code}&product={product}')`. Returns JSON with `set_code`, `product`, `total_weight`, `variants` array, and `sheets` object.
- Content area is rebuilt entirely: one Variants section (open) + one section per sheet (collapsed).

### Collapsible Sections

- Each section is a `.section` div. Clicking the `.section-header` toggles the `open` class.
- When `open`: the `.section-body` is visible (`display: block`), and the arrow rotates 90 degrees.
- When collapsed: the body is hidden (`display: none`), arrow points right.
- The Variants section defaults to open. All sheet sections default to collapsed.

### Card Grid Column Count

- Stored in CSS custom property `--grid-cols` on `<html>`.
- Default: 6 columns on desktop (viewport >= 600px), 3 on mobile.
- Persisted in `localStorage` as `exploreGridCols`. Restored on next page load.
- Range: 1 to 12 columns.

### Zoom Overlay

- Triggered by clicking any `.sheet-card` element. Sets `#zoom-img` src and adds class `active` to `#zoom-overlay`.
- `active` class changes `display` from `none` to `flex`.
- Dismissed by clicking anywhere on the overlay (removes `active` class).

### Card Badges (Per Card)

Badges are generated dynamically based on card data and settings:
- **Pull rate badge** (`span.badge.pull-rate`): Always shown. Displays `{pull_rate * 100}%`.
- **Scryfall badge** (`a.badge.link`): Shown if `price_sources` setting includes `tcg` AND card has a `printing_id`. Displays "SF" + optional TCG price.
- **Card Kingdom badge** (`a.badge.link`): Shown if `price_sources` setting includes `ck` AND card has a `ck_url`. Displays "CK" + optional CK price.
- **Treatment badges** (`span.badge.treatment`): Conditionally shown:
  - "BL" if `border_color === 'borderless'`
  - "SC" if `frame_effects` includes `'showcase'`
  - "EA" if `frame_effects` includes `'extendedart'`
  - "FA" if `is_full_art` is true

### Foil Visual Treatment

- Cards with `foil: true` get the class `foil` on `.sheet-card-img-wrap`.
- Foil cards display a rainbow gradient overlay (`::before` pseudo-element with `mix-blend-mode: color`).
- Foil cards also display an animated light streak (`::after` pseudo-element with `foil-streak` keyframe animation, 3s infinite).

### Card Border Colors

- **Rarity gradient**: Top of card border is colored by rarity — common (#111 dark), uncommon (#6a6a6a gray), rare (#c9a816 gold), mythic (#d4422a red-orange).
- **Set gradient**: Bottom of card border is #111 (dark) for cards from the main set, or #5c2d91 (purple) for "guest" cards from a different set (e.g., The List, bonus sheets).
- Applied via CSS custom properties `--rarity-color` and `--set-color` with `linear-gradient(to bottom, ...)`.

### Sheet Name Prettification

- camelCase sheet names like `rareMythicWithShowcase` are converted to space-separated title case: "Rare Mythic With Showcase".
- Applied via `prettifySheetName()` regex.

### Variant Pills

- Each variant row in the Variants table shows pills for each sheet it pulls from.
- Foil sheets get a distinct gradient pill style (`.foil-pill`).
- Format: `{count} x {Sheet Name}`.

### Subgroup Headers

- Cards within each sheet are grouped by `(set_code, rarity, weight)`.
- Groups are sorted: main set first, then guest sets; within each, by rarity order (common < uncommon < rare < mythic); within same rarity, by weight descending.
- Each subgroup header shows: `{Rarity}: {subWeight}/{totalWeight} ({pct}%) [a card: {cardWeight}/{totalWeight}; {pct}%]`
- For guest set cards, the header also includes the set name and code.

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When Called | Returns | Required For |
|----------|--------|-------------|---------|--------------|
| `/api/settings` | GET | Page load (fire and forget) | `{image_display, price_sources, price_floor, demo_loaded}` | Determining which price badges to show (TCG, CK, or both) |
| `/api/sets` | GET | Page load | Array of `{code, name}` | Populating the searchable set dropdown |
| `/api/products?set={code}` | GET | After set selection | Array of product name strings (e.g., `["collector", "play", "prerelease"]`) | Populating product radio buttons |
| `/api/sheets?set={code}&product={product}` | GET | After set+product selection | `{set_code, product, total_weight, variants: [...], sheets: {...}}` | Rendering the entire sheet/card display |

### Data Shape: `/api/sheets` Response

```json
{
  "set_code": "blb",
  "product": "play",
  "total_weight": 1000,
  "variants": [
    {
      "index": 0,
      "weight": 788,
      "probability": 0.788,
      "contents": {"common": 7, "foil": 1, "land": 1, "rareMythicWithShowcase": 1, "uncommon": 3, "wildcard": 1}
    }
  ],
  "sheets": {
    "common": {
      "foil": false,
      "card_count": 81,
      "total_weight": 324,
      "cards": [
        {
          "uuid": "...",
          "name": "Card Name",
          "set_code": "blb",
          "collector_number": "1",
          "rarity": "common",
          "printing_id": "...",
          "image_uri": "https://cards.scryfall.io/...",
          "weight": 4,
          "pull_rate": 0.012,
          "foil": false,
          "border_color": "black",
          "frame_effects": [],
          "is_full_art": false,
          "ck_url": "https://...",
          "ck_price": null,
          "tcg_price": null
        }
      ]
    }
  }
}
```

### Data That Must Exist

- At least one set must be loaded in the database (from MTGJSON/Scryfall cache) for the sets dropdown to populate.
- MTGJSON booster data must be imported for the selected set/product combination, otherwise the sheets API returns an error.
- Card images require Scryfall CDN access (external network) for rendering, though the data itself is local.

---

## 7. Visual States

### Initial Load State
- Set input: disabled, placeholder "Loading sets..."
- Product radios: empty
- Pack button: disabled
- Content area: shows empty state message "Select a set and product to explore booster sheets"
- Status: "Loading sets..."

### Sets Loaded, No Selection
- Set input: enabled, placeholder "Search sets..."
- Product radios: empty
- Pack button: disabled
- Content area: shows empty state "Select a set and product to explore booster sheets"
- Status: "{N} sets loaded"

### Set Dropdown Open
- Dropdown list (`#set-dropdown`) visible below the input with class `open`
- Shows all sets or filtered subset
- Active item (keyboard-navigated) highlighted with `.active` class

### Set Selected, Products Loading
- Set input: shows `"{Set Name} ({code})"`
- Product radios: shows "Loading..." text
- Pack button: disabled
- Content area: previous content or initial empty state

### Set and Product Selected, Sheets Loading
- Product radio pills visible; one highlighted (red)
- Pack button: enabled
- Content area: shows "Loading sheets..." empty state
- Status: "Loading..."

### Sheets Loaded (Normal State)
- Variants section: expanded, showing a table with columns #, Probability, Contents
- Sheet sections: collapsed, each header showing sheet name, card count, foil tag (if applicable), and which variants use it
- Status: "{N} sheets, {M} cards"
- Pack button: enabled

### Sheet Section Expanded
- Arrow rotated 90 degrees
- Body visible with subgroup containers
- Each subgroup: header with rarity/odds, followed by a card grid
- Cards show: image with rarity/set border gradient, optional foil effect, badges (pull rate, prices, treatments)

### Zoom Overlay Active
- Full-screen dark overlay (`rgba(0,0,0,0.75)`)
- Single large card image centered (max 85vh height, 90vw width)
- Cursor shows pointer (click to dismiss)

### Error State
- If `/api/sheets` returns `{error: "..."}`, the content area shows the error message in the empty state style (italic, centered, gray text)
- Status text is cleared

### No Products Available
- If `/api/products` returns an empty array, no radio buttons appear
- Pack button remains disabled
- Sheets do not load (no automatic `onSelectionChange` call)

### Deep-Linked State
- When URL hash contains `set=X&product=Y`, the page auto-selects the set and product on load
- Behaves identically to the "Sheets Loaded" state after auto-selection completes
