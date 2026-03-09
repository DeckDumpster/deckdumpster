# Set Value Analysis — UX Description

## Page Purpose

The Set Value Analysis page (`/set-value`) allows users to analyze the price distribution of cards across one or more MTG sets. Users select sets from a searchable multi-select dropdown, choose a price source (TCGplayer or Card Kingdom) and price type (Normal or Foil), then click Analyze to see a histogram chart of card counts across price buckets, summary statistics (total cards, median price, percentage breakdowns by value tier), and a table of the top 20 most valuable cards. The page supports extensive client-side filtering by rarity, color, card type (normal vs. special treatments), ownership status, and price thresholds, with a split-by feature to break down the chart by rarity, color, or owned/unowned status. Clicking a bar on the chart opens a Scryfall search for the matching cards in that price range.

## Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| Left arrow + "Home" link | `<a href="/">` | Homepage (`/`) | Header, left side |
| "Set Value Analysis" | `<h1>` (not a link) | N/A | Header, right of home link |
| Card name links in Top 20 table | `<a>` per row | Scryfall card page (`https://scryfall.com/card/{set_code}/{collector_number}`) | Top cards table, "Card" column |
| Chart bar click | JS click handler | Scryfall search URL (opens in new tab) | Chart area |

## Interactive Elements

### Controls Row (top of page)

| Element | ID | Type | Default | Behavior |
|---------|----|------|---------|----------|
| Set search input | `set-search` | `<input type="text">` | Empty, placeholder "Search sets..." | On focus: opens dropdown. On input: filters dropdown list. Dropdown shows up to 50 matching sets from `/api/cached-sets`. |
| Set dropdown | `set-dropdown` | `<ul>` with dynamic `<li>` items | Hidden | Opens on input focus, closes on blur (150ms delay). Click a set to toggle selection. Selected sets show in red text with `.selected` class. |
| Selected set pills | `selected-pills` | Container `<div>` with dynamic `<span>` pills | Empty | Each selected set renders as a pill with set name, code, and an "x" remove button (`.remove-pill`). Clicking "x" deselects the set. |
| Price source toggle | `source-toggle` | Toggle group (exclusive pills) | "TCGplayer" active | Options: `tcgplayer`, `cardkingdom`. Switching rebuilds chart if data is loaded. |
| Price type toggle | `type-toggle` | Toggle group (exclusive pills) | "Normal" active | Options: `normal`, `foil`. Switching rebuilds chart if data is loaded. |
| Analyze button | `analyze-btn` | `<button>` | Disabled | Enabled when at least one set is selected. Triggers POST to `/api/set-value-data` with selected sets, source, and price type. |

### Filter Bar (appears after analysis)

| Element | ID | Type | Default | Behavior |
|---------|----|------|---------|----------|
| Split-by toggle | `split-toggle` | Toggle group (exclusive) | "None" active | Options: `none` (one dataset per set), `rarity` (stacked by C/U/R/M), `color` (stacked by WUBRGCM), `owned` (stacked owned vs. not owned). Changes chart dataset grouping; stacked when not "None". |
| Cards type toggle | `card-type-toggle` | Toggle group (exclusive) | "All" active | Options: `all`, `normal` (excludes special treatments), `special` (only extended art, showcase, full art, borderless, promo cards). Filters card list before chart render. |
| Owned toggle | `owned-toggle` | Toggle group (exclusive) | "All" active | Options: `all`, `owned` (only cards in collection), `unowned` (only cards not in collection). Filters card list before chart render. |
| Price operator toggle | `price-op-toggle` | Toggle group (exclusive) | "Off" active | Options: `off` (no price filter), `gte` (>=), `lte` (<=). When active, filters cards by price compared to the price threshold input. Cards with null prices are excluded when any price filter is active. |
| Price threshold input | `price-filter-val` | `<input type="number">` | `1` (min=0, step=1) | Dollar threshold for the price filter. Changes trigger chart rebuild when price filter is not "Off". |
| Rarity filter pills | `rarity-filters` | Check row (multi-toggle) | All active (C, U, R, M) | Values: `common`, `uncommon`, `rare`, `mythic`. Each pill toggles independently. Deactivating a rarity excludes those cards. |
| Color filter pills | `color-filters` | Check row (multi-toggle) | All active (W, U, B, R, G, C, Multi) | Values: `W`, `U`, `B`, `R`, `G`, `C`, `M`. Each pill toggles independently. Color is determined by card's `colors` JSON array: empty = Colorless, 1 color = that color, 2+ colors = Multi. |

### Chart

| Element | ID | Type | Behavior |
|---------|-----|------|----------|
| Chart canvas | `chart` | `<canvas>` (Chart.js bar chart) | Renders price distribution histogram. X-axis: 10 price buckets ($0-0.10, $0.10-0.25, $0.25-0.50, $0.50-1, $1-2, $2-5, $5-10, $10-20, $20-50, $50+). Y-axis: card count. Tooltip shows "{Dataset label}: {count} cards". Clicking a bar opens Scryfall search in new tab for matching set+rarity/color+price range. |
| Chart wrapper | `chart-wrap` | `<div>` | 500px tall container with dark background. Hidden until analysis completes. |

### Summary Stats

| Element | ID | Content |
|---------|-----|---------|
| Total Cards | `stat-total` | Count of filtered cards |
| With Prices | `stat-priced` | Count of cards that have a non-null price |
| Median | `stat-median` | Median price of priced cards, formatted as `$X.XX` |
| Chaff % | `stat-chaff` | Percentage of priced cards under $0.40 |
| Modest % | `stat-modest` | Percentage of priced cards $0.40-$2 |
| High % | `stat-high` | Percentage of priced cards $2-$10 |
| Premium % | `stat-premium` | Percentage of priced cards $10+ |

### Top 20 Table

| Column | Content |
|--------|---------|
| # | Rank (1-20) |
| Card | Card name, linked to Scryfall card page (opens in new tab) |
| Set | Set code (uppercase) |
| CN | Collector number |
| Rarity | Single letter: C/U/R/M |
| Finishes | Color-coded treatment tags: Foil (gold), Etched (gray-purple), Borderless (green), Showcase (purple), Extended Art (brown), Full Art (teal), Promo (red) |
| Owned | Green badge with count if owned, empty if not |
| Price | Dollar-formatted price |

## User Flows

### Flow 1: Basic Set Value Analysis

1. Page loads. The empty state message is shown: "Select one or more sets and click Analyze to view value distribution."
2. On page load, `GET /api/cached-sets` is called to populate the set list.
3. User clicks or focuses the "Search sets..." input field.
4. The dropdown opens showing up to 50 sets (all sets if no filter text).
5. User types a partial set name or code to filter the list.
6. User clicks a set in the dropdown. The set is added to `selectedSets`, a pill appears below the input, and the Analyze button becomes enabled.
7. User optionally selects additional sets (multi-select; all appear as pills).
8. User optionally switches price source from TCGplayer to Card Kingdom.
9. User optionally switches price type from Normal to Foil.
10. User clicks "Analyze".
11. The empty state hides. The "Loading card data..." message appears.
12. A POST request to `/api/set-value-data` is sent with `{ sets: [...], source: "tcgplayer"|"cardkingdom", price_type: "normal"|"foil" }`.
13. On response, the loading message hides. The filter bar, summary stats, chart, and top 20 table all appear.
14. The chart displays a bar histogram with one dataset per selected set (when split is "None"), color-coded from a palette of 8 colors.
15. Summary stats update with total cards, priced count, median, and tier percentages.
16. The top 20 table shows the 20 highest-priced cards across all selected sets with treatment tags and ownership badges.

### Flow 2: Removing a Selected Set

1. User has one or more sets selected (pills visible below the input).
2. User clicks the "x" on a set pill.
3. The set is removed from selection. The pill disappears.
4. If no sets remain selected, the Analyze button becomes disabled.
5. The previously loaded chart/data remains visible until the user clicks Analyze again.

### Flow 3: Filtering Results After Analysis

1. User has completed an analysis (chart, stats, and table visible).
2. User clicks a rarity pill (e.g., deactivates "C" to hide commons). The chart, summary, and top 20 table immediately rebuild with the filtered subset.
3. User clicks a color pill (e.g., deactivates "R" to hide red cards). Immediate rebuild.
4. User switches "Cards" toggle to "Special" to see only extended art, showcase, borderless, full art, and promo cards. Immediate rebuild.
5. User switches "Owned" toggle to "Owned" to see only cards in their collection. Immediate rebuild.
6. User activates price filter by clicking ">=" and adjusting the threshold to $5. Only cards priced $5 or more are shown. Cards without prices are excluded. Immediate rebuild.
7. All filters compose together (intersection). The chart, summary stats, and top 20 table all reflect the currently filtered subset.

### Flow 4: Splitting the Chart

1. User has completed an analysis.
2. User clicks "Rarity" in the Split-by toggle. The chart becomes a stacked bar chart with four series (Common=gray, Uncommon=silver, Rare=gold, Mythic=red), showing how each rarity contributes to each price bucket.
3. User clicks "Color" in the Split-by toggle. The chart switches to seven series (White, Blue, Black, Red, Green, Colorless, Multicolor) with MTG-themed colors.
4. User clicks "Owned" in the Split-by toggle. The chart shows two series: Owned (green) and Not Owned (gray).
5. User clicks "None" to return to one-dataset-per-set mode (ungrouped bars).

### Flow 5: Clicking a Chart Bar to View on Scryfall

1. User has chart data displayed.
2. User clicks on a specific bar segment in the chart.
3. A Scryfall search URL is constructed based on the set code(s), the price bin's range, the split key (if applicable, e.g., rarity or color), and the current price type (uses `usd` for normal, `usd_foil` for foil).
4. The Scryfall search page opens in a new browser tab.

### Flow 6: Viewing Card Details from Top 20 Table

1. User scrolls to the Top 20 Most Valuable Cards table.
2. User clicks a card name link.
3. The Scryfall card page (`https://scryfall.com/card/{set}/{cn}`) opens in a new tab.

### Flow 7: Re-analyzing with Different Parameters

1. User has already analyzed one or more sets.
2. User changes the price source toggle (e.g., from TCGplayer to Card Kingdom).
3. User clicks "Analyze" again.
4. The loading state appears, a new POST request is sent with the updated source, and results refresh.
5. Alternatively, the user adds/removes sets and clicks Analyze to get new data.

Note: Changing the source or type toggle *after* data is loaded does NOT automatically re-fetch data. However, if data is already loaded (`allCards.length > 0`), toggling source/type calls `buildChart()` which re-renders the chart using the existing data. This means the chart will re-render but the underlying data still reflects the original source/type from the last fetch. The user must click Analyze again to actually fetch new price data from the different source.

## Dynamic Behavior

### On Page Load
- `loadSets()` fires immediately, calling `GET /api/cached-sets`. On success, it initializes the multi-select dropdown with the returned set list.
- All toggle groups (`source-toggle`, `type-toggle`, `split-toggle`, `card-type-toggle`, `owned-toggle`, `price-op-toggle`) and check rows (`rarity-filters`, `color-filters`) are initialized with click handlers.
- The price input (`price-filter-val`) gets an `input` event listener that rebuilds the chart when the price filter is active and data is loaded.
- The Analyze button gets a click handler bound to `analyze()`.

### On Analyze Click
- Hides: `empty-state`, `filter-bar`, `summary`, `chart-wrap`, `top-cards`.
- Shows: `loading` (adds `.visible` class).
- Sends POST to `/api/set-value-data`.
- On response: hides loading, shows `filter-bar`, `summary`, `chart-wrap`, `top-cards`.
- Calls `buildChart()` which runs `filterCards()` then renders the Chart.js bar chart and updates summary stats and top 20 table.

### On Any Filter/Toggle Change (after data loaded)
- If `allCards.length > 0`, changing any toggle or check-row pill calls `buildChart()`.
- `buildChart()` calls `filterCards()` to apply all active filters, then bins the filtered cards into price buckets, creates Chart.js datasets based on split mode, destroys and recreates the chart, and calls `updateSummary()` and `updateTopCards()`.
- No network request is made -- all filtering is client-side on the `allCards` array.

### Chart Interactivity
- Hovering a bar shows a tooltip: "{Dataset label}: {count} cards".
- Clicking a bar constructs and opens a Scryfall search URL in a new tab.
- The chart legend is interactive (Chart.js default) -- clicking legend items can toggle dataset visibility.

### Multi-Select Dropdown
- Opens on input focus or input change.
- Closes on input blur after a 150ms delay (to allow click events on dropdown items to register).
- Filters are case-insensitive, matching against `"{name} ({code})"`.
- Limited to 50 items in the dropdown at a time.
- Already-selected sets are highlighted with red text (`.selected` class).
- Clicking a set toggles its selection (add if not selected, remove if selected).

## Data Dependencies

### API Endpoints

| Endpoint | Method | Request | Response | When Called |
|----------|--------|---------|----------|-------------|
| `/api/cached-sets` | GET | None | `[{ "code": "lci", "name": "The Lost Caverns of Ixalan" }, ...]` | On page load |
| `/api/set-value-data` | POST | `{ "sets": ["lci", "mkm"], "source": "tcgplayer"\|"cardkingdom", "price_type": "normal"\|"foil" }` | Array of card objects (see below) | On Analyze click |

### Card Object Shape (from `/api/set-value-data`)

```json
{
  "name": "Card Name",
  "set_code": "lci",
  "set_name": "The Lost Caverns of Ixalan",
  "collector_number": "150",
  "rarity": "rare",
  "colors": "[\"R\"]",
  "price": 4.50,
  "finishes": "[\"nonfoil\",\"foil\"]",
  "frame_effects": "[\"extendedart\"]",
  "border_color": "black",
  "full_art": 0,
  "promo": 0,
  "promo_types": "[]",
  "owned": 2
}
```

Notes:
- `colors`, `finishes`, `frame_effects`, and `promo_types` are JSON-encoded strings (parsed with `JSON.parse()` on the client).
- `price` can be `null` if no price data exists for the requested source/type.
- `owned` is an integer count of collection entries for that printing.
- Card Kingdom prices are stored with `buylist_` prefix internally (the server maps `price_type` to `buylist_normal` or `buylist_foil` for CK).

### Data Prerequisites
- Sets must be cached (have `cards_fetched_at` populated in the `sets` table) to appear in the dropdown. Run `mtg cache all` if the dropdown is empty.
- Price data must exist in the `prices` table for the selected source/type. Without price data, cards will have `price: null` and won't appear in the chart or top 20 table (though they still count toward "Total Cards" in the summary).

## Visual States

### State 1: Initial / Empty State
- **Visible:** Header with home link and title. Set search input (empty). Source toggle (TCGplayer active). Type toggle (Normal active). Analyze button (disabled, grayed out). Empty state message: "Select one or more sets and click Analyze to view value distribution."
- **Hidden:** Selected pills area (empty), filter bar, summary stats, chart, loading indicator, top 20 table.

### State 2: Sets Selected, Pre-Analysis
- **Visible:** Same as State 1 plus selected set pills below the search input. Analyze button is now enabled (red, clickable).
- **Hidden:** Filter bar, summary stats, chart, loading indicator, top 20 table.
- **Empty state message still visible.**

### State 3: Loading
- **Visible:** Header, controls row, selected pills. Loading indicator: "Loading card data..." (centered, gray text).
- **Hidden:** Empty state, filter bar, summary, chart, top 20 table.

### State 4: Results Loaded (default filters)
- **Visible:** Header, controls row, selected pills, filter bar (all filters at defaults), summary stats row, chart (bar histogram, 500px tall), top 20 table.
- **Hidden:** Empty state, loading indicator.
- Chart shows one color-coded dataset per selected set (when split is "None").
- Summary shows aggregate stats for all cards in the selected sets.

### State 5: Results Loaded with Active Filters
- Same layout as State 4, but chart/summary/table reflect filtered subset.
- Deactivated filter pills lose their red background and appear gray.
- Price filter input is always visible but only effective when price operator is not "Off".

### State 6: Results with Split Active
- Same as State 4/5, but the chart is stacked.
- Split by rarity: 4 series (Common=gray, Uncommon=silver, Rare=gold, Mythic=red).
- Split by color: 7 series (White=near-white, Blue=blue, Black=purple-gray, Red=red, Green=green, Colorless=gray, Multicolor=gold).
- Split by owned: 2 series (Owned=green, Not Owned=dark gray).
- Legend labels update to reflect split categories instead of set names.

### State 7: No Priced Cards (edge case)
- If all cards in the selected sets have `price: null`, the chart renders with all-zero bins.
- Summary shows Total Cards > 0 but With Prices = 0, Median = $0.00, all tier percentages = 0%.
- Top 20 table body is empty (no rows).

### State 8: Dropdown Open
- The set dropdown (`#set-dropdown`) gains the `.open` class and becomes visible, positioned absolutely below the search input.
- Up to 50 matching sets are listed. Scrollable if more than fit in 200px max-height.
- Already-selected sets appear with red text.

### State 9: Multiple Sets Compared (split = None)
- When 2+ sets are selected and split mode is "None", the chart renders grouped (non-stacked) bars with a different color per set from the 8-color palette.
- The legend shows each set's name and code.
