# Set Value Analysis (`/set-value`) -- Test Plan

Source: `tests/ui/ux-descriptions/set-value.md`

## Existing Coverage

No existing intents cover the `/set-value` page. All intents below are new.

---

## Proposed Intents

### set_value_initial_state
- **Description**: When I visit `/set-value`, I see the page header with a left arrow and "Home" link, the "Set Value Analysis" title, the set search input with "Search sets..." placeholder, the price source toggle with "TCGplayer" active, the price type toggle with "Normal" active, and a disabled "Analyze" button. The empty state message reads "Select one or more sets and click Analyze to view value distribution." The chart, filter bar, summary stats, and top 20 table are all hidden.
- **References**: Visual States (State 1: Initial / Empty State), Interactive Elements (Controls Row), Navigation
- **Testability**: full
- **Priority**: high

### set_value_select_set_and_pills
- **Description**: I focus the "Search sets..." input and a dropdown of sets appears. I type a partial name to filter the list, then click a set to select it. A pill appears below the input showing the set name, code, and an "x" remove button. The Analyze button becomes enabled (red, clickable). The selected set appears in red text in the dropdown if I open it again.
- **References**: User Flows (Flow 1: steps 3-6), Interactive Elements (set-search, set-dropdown, selected-pills), Visual States (State 2, State 8), Dynamic Behavior (Multi-Select Dropdown)
- **Testability**: full
- **Priority**: high

### set_value_remove_set_pill
- **Description**: After selecting two or more sets, I click the "x" on one of the set pills. That pill disappears and the set is deselected. If I remove all pills, the Analyze button becomes disabled again. The previously loaded chart data remains visible until I click Analyze.
- **References**: User Flows (Flow 2: Removing a Selected Set), Interactive Elements (selected-pills, .remove-pill)
- **Testability**: full
- **Priority**: medium

### set_value_basic_analysis
- **Description**: I select a set, click "Analyze", and see the loading message "Loading card data..." appear. After loading completes, the filter bar, chart (a bar histogram with price buckets on the x-axis), summary stats row, and the Top 20 Most Valuable Cards table all become visible. The empty state message and loading indicator are hidden.
- **References**: User Flows (Flow 1: steps 10-16), Visual States (State 3: Loading, State 4: Results Loaded), Dynamic Behavior (On Analyze Click)
- **Testability**: full
- **Priority**: high

### set_value_summary_stats
- **Description**: After running an analysis, the summary stats row shows: Total Cards count, With Prices count, Median price formatted as "$X.XX", and four tier percentages -- Chaff (under $0.40), Modest ($0.40-$2), High ($2-$10), and Premium ($10+). All percentages are displayed and sum to approximately 100%.
- **References**: Interactive Elements (Summary Stats: stat-total, stat-priced, stat-median, stat-chaff, stat-modest, stat-high, stat-premium)
- **Testability**: full
- **Priority**: high

### set_value_top_20_table
- **Description**: After running an analysis, the Top 20 Most Valuable Cards table displays up to 20 rows ranked by price. Each row shows rank number, card name (as a Scryfall link), set code, collector number, rarity letter, color-coded finish/treatment tags, an ownership badge (green with count if owned, empty if not), and the dollar price.
- **References**: Interactive Elements (Top 20 Table), User Flows (Flow 6: Viewing Card Details)
- **Testability**: full
- **Priority**: high

### set_value_top_20_card_link
- **Description**: In the Top 20 table, I click on a card name link. The link targets the Scryfall card page at `https://scryfall.com/card/{set}/{cn}` and opens in a new tab.
- **References**: Navigation (Card name links in Top 20 table), User Flows (Flow 6)
- **Testability**: limited (new tab opens externally; can verify href attribute but not the tab opening)
- **Priority**: medium

### set_value_filter_rarity
- **Description**: After an analysis, the filter bar shows rarity pills (C, U, R, M) all active. I deactivate the "C" (Common) pill. The chart, summary stats, and top 20 table immediately rebuild to exclude common cards. The deactivated pill appears gray instead of red. I reactivate it and the commons return.
- **References**: User Flows (Flow 3: step 2), Interactive Elements (rarity-filters), Dynamic Behavior (On Any Filter/Toggle Change)
- **Testability**: full
- **Priority**: high

### set_value_filter_color
- **Description**: After an analysis, the filter bar shows color pills (W, U, B, R, G, C, Multi) all active. I deactivate the "R" (Red) pill. The chart and stats immediately rebuild to exclude red cards. I reactivate it and the red cards return.
- **References**: User Flows (Flow 3: step 3), Interactive Elements (color-filters), Dynamic Behavior (On Any Filter/Toggle Change)
- **Testability**: full
- **Priority**: medium

### set_value_filter_card_type
- **Description**: After an analysis, I switch the "Cards" toggle to "Special" to see only extended art, showcase, borderless, full art, and promo cards. The chart, summary, and top 20 table rebuild with only special treatment cards. Switching to "Normal" shows only non-special cards. Switching back to "All" shows everything.
- **References**: User Flows (Flow 3: step 4), Interactive Elements (card-type-toggle)
- **Testability**: full
- **Priority**: medium

### set_value_filter_owned
- **Description**: After an analysis, I switch the "Owned" toggle to "Owned" to see only cards in my collection. The chart, summary, and top 20 table rebuild with only owned cards. Switching to "Unowned" shows only cards not in the collection. Switching back to "All" shows everything.
- **References**: User Flows (Flow 3: step 5), Interactive Elements (owned-toggle)
- **Testability**: full
- **Priority**: medium

### set_value_filter_price_threshold
- **Description**: After an analysis, the price filter defaults to "Off". I click ">=" and set the threshold to 5. The chart, summary, and top 20 table rebuild to show only cards priced $5 or more. Cards without prices are excluded. I switch to "<=" and the chart shows only cards priced $5 or less. I switch back to "Off" and all cards return.
- **References**: User Flows (Flow 3: step 6), Interactive Elements (price-op-toggle, price-filter-val)
- **Testability**: full
- **Priority**: medium

### set_value_filters_compose
- **Description**: After an analysis, I apply multiple filters simultaneously -- deactivate common rarity, set owned to "Owned", and activate a ">=" price filter of $2. All filters compose together as an intersection. The chart, summary, and top 20 table reflect only the cards matching all active filter criteria.
- **References**: User Flows (Flow 3: step 7), Dynamic Behavior (On Any Filter/Toggle Change)
- **Testability**: full
- **Priority**: medium

### set_value_split_by_rarity
- **Description**: After an analysis, I click "Rarity" in the Split-by toggle. The chart becomes a stacked bar chart with four series (Common in gray, Uncommon in silver, Rare in gold, Mythic in red). The legend updates to show the rarity categories instead of set names.
- **References**: User Flows (Flow 4: step 2), Visual States (State 6), Interactive Elements (split-toggle)
- **Testability**: full
- **Priority**: high

### set_value_split_by_color
- **Description**: After an analysis, I click "Color" in the Split-by toggle. The chart switches to a stacked bar chart with seven series (White, Blue, Black, Red, Green, Colorless, Multicolor) using MTG-themed colors. The legend reflects the color categories.
- **References**: User Flows (Flow 4: step 3), Visual States (State 6)
- **Testability**: full
- **Priority**: medium

### set_value_split_by_owned
- **Description**: After an analysis, I click "Owned" in the Split-by toggle. The chart shows two stacked series: Owned (green) and Not Owned (dark gray). I click "None" to return to one-dataset-per-set mode with ungrouped bars.
- **References**: User Flows (Flow 4: steps 4-5), Visual States (State 6)
- **Testability**: full
- **Priority**: medium

### set_value_chart_bar_click_scryfall
- **Description**: After an analysis, I click on a bar segment in the chart. A Scryfall search URL is constructed based on the set code, the price bin range, the split key (if any), and the current price type, and it opens in a new browser tab.
- **References**: User Flows (Flow 5: Clicking a Chart Bar), Navigation (Chart bar click), Chart Interactivity
- **Testability**: limited (new tab opens externally; can verify the URL construction logic but not the actual navigation)
- **Priority**: medium

### set_value_reanalyze_different_source
- **Description**: After analyzing with TCGplayer prices, I switch the price source toggle to "Card Kingdom" and click "Analyze" again. A new POST request is sent with the updated source, the loading state appears, and the results refresh with Card Kingdom pricing.
- **References**: User Flows (Flow 7: Re-analyzing with Different Parameters), Dynamic Behavior (On Analyze Click)
- **Testability**: full
- **Priority**: medium

### set_value_toggle_price_type_foil
- **Description**: I select a set, switch the price type toggle from "Normal" to "Foil", and click "Analyze". The results display foil pricing. The chart, summary, and top 20 table all reflect foil prices instead of normal prices.
- **References**: User Flows (Flow 1: step 9), Interactive Elements (type-toggle)
- **Testability**: full
- **Priority**: medium

### set_value_multi_set_comparison
- **Description**: I select two or more sets and click "Analyze". The chart renders grouped (non-stacked) bars with a different color per set from the 8-color palette. The legend shows each set's name and code. The summary and top 20 table aggregate data across all selected sets.
- **References**: Visual States (State 9: Multiple Sets Compared), User Flows (Flow 1: steps 7, 14)
- **Testability**: full
- **Priority**: high

### set_value_set_search_filter
- **Description**: I type a partial set name or code into the search input and the dropdown filters to show only matching sets. The filter is case-insensitive, matching against the full "Name (code)" string. The dropdown shows up to 50 matching results and is scrollable if more would fit.
- **References**: Interactive Elements (set-search, set-dropdown), Dynamic Behavior (Multi-Select Dropdown)
- **Testability**: full
- **Priority**: medium

### set_value_dropdown_selected_highlight
- **Description**: After selecting a set, I open the dropdown again. The selected set appears with red text and a `.selected` class. I click it again to deselect it -- the set is removed from selection, the pill disappears, and the dropdown item returns to normal text color.
- **References**: Dynamic Behavior (Multi-Select Dropdown), Interactive Elements (set-dropdown)
- **Testability**: full
- **Priority**: low

### set_value_home_link_navigation
- **Description**: I visit `/set-value` and click the left arrow / "Home" link in the header. I am navigated to the homepage (`/`).
- **References**: Navigation (Left arrow + "Home" link)
- **Testability**: full
- **Priority**: low

### set_value_no_priced_cards_edge_case
- **Description**: When I analyze a set where all cards have null prices, the chart renders with all-zero bins. The summary shows Total Cards greater than zero but With Prices equals zero, Median is $0.00, and all tier percentages are 0%. The Top 20 table body is empty with no rows.
- **References**: Visual States (State 7: No Priced Cards)
- **Testability**: limited (requires a set with no price data in the test fixture; may not be available without special fixture setup)
- **Priority**: low

### set_value_chart_tooltip_hover
- **Description**: After an analysis, I hover over a bar in the chart. A tooltip appears showing "{Dataset label}: {count} cards" with the exact count of cards in that price bucket.
- **References**: Dynamic Behavior (Chart Interactivity), Interactive Elements (Chart)
- **Testability**: limited (hover interaction on canvas elements is difficult to verify precisely with screenshot-based testing)
- **Priority**: low

### set_value_chart_legend_toggle
- **Description**: After analyzing multiple sets, the chart legend shows one entry per set. I click a legend item to toggle its dataset visibility off. The corresponding bars disappear from the chart. Clicking the legend item again restores them.
- **References**: Dynamic Behavior (Chart Interactivity -- legend is interactive)
- **Testability**: limited (Chart.js legend click behavior on canvas is difficult to automate reliably)
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| Page Purpose | `set_value_initial_state`, `set_value_basic_analysis` |
| Navigation > Home link | `set_value_home_link_navigation` |
| Navigation > Card name links (Top 20) | `set_value_top_20_card_link` |
| Navigation > Chart bar click | `set_value_chart_bar_click_scryfall` |
| Interactive Elements > Controls Row (set-search) | `set_value_select_set_and_pills`, `set_value_set_search_filter` |
| Interactive Elements > Controls Row (set-dropdown) | `set_value_select_set_and_pills`, `set_value_dropdown_selected_highlight`, `set_value_set_search_filter` |
| Interactive Elements > Controls Row (selected-pills) | `set_value_select_set_and_pills`, `set_value_remove_set_pill` |
| Interactive Elements > Controls Row (source-toggle) | `set_value_initial_state`, `set_value_reanalyze_different_source` |
| Interactive Elements > Controls Row (type-toggle) | `set_value_initial_state`, `set_value_toggle_price_type_foil` |
| Interactive Elements > Controls Row (analyze-btn) | `set_value_initial_state`, `set_value_select_set_and_pills`, `set_value_basic_analysis` |
| Interactive Elements > Filter Bar (split-toggle) | `set_value_split_by_rarity`, `set_value_split_by_color`, `set_value_split_by_owned` |
| Interactive Elements > Filter Bar (card-type-toggle) | `set_value_filter_card_type` |
| Interactive Elements > Filter Bar (owned-toggle) | `set_value_filter_owned` |
| Interactive Elements > Filter Bar (price-op-toggle, price-filter-val) | `set_value_filter_price_threshold` |
| Interactive Elements > Filter Bar (rarity-filters) | `set_value_filter_rarity` |
| Interactive Elements > Filter Bar (color-filters) | `set_value_filter_color` |
| Interactive Elements > Chart | `set_value_basic_analysis`, `set_value_chart_bar_click_scryfall`, `set_value_chart_tooltip_hover`, `set_value_chart_legend_toggle` |
| Interactive Elements > Summary Stats | `set_value_summary_stats` |
| Interactive Elements > Top 20 Table | `set_value_top_20_table`, `set_value_top_20_card_link` |
| User Flow 1: Basic Analysis | `set_value_initial_state`, `set_value_select_set_and_pills`, `set_value_basic_analysis`, `set_value_summary_stats`, `set_value_top_20_table` |
| User Flow 2: Removing a Set | `set_value_remove_set_pill` |
| User Flow 3: Filtering Results | `set_value_filter_rarity`, `set_value_filter_color`, `set_value_filter_card_type`, `set_value_filter_owned`, `set_value_filter_price_threshold`, `set_value_filters_compose` |
| User Flow 4: Splitting the Chart | `set_value_split_by_rarity`, `set_value_split_by_color`, `set_value_split_by_owned` |
| User Flow 5: Chart Bar Click | `set_value_chart_bar_click_scryfall` |
| User Flow 6: Top 20 Card Details | `set_value_top_20_card_link` |
| User Flow 7: Re-analyzing | `set_value_reanalyze_different_source`, `set_value_toggle_price_type_foil` |
| Dynamic Behavior > On Page Load | `set_value_initial_state` |
| Dynamic Behavior > On Analyze Click | `set_value_basic_analysis` |
| Dynamic Behavior > On Filter/Toggle Change | `set_value_filter_rarity`, `set_value_filter_color`, `set_value_filter_card_type`, `set_value_filter_owned`, `set_value_filter_price_threshold`, `set_value_filters_compose` |
| Dynamic Behavior > Chart Interactivity | `set_value_chart_tooltip_hover`, `set_value_chart_bar_click_scryfall`, `set_value_chart_legend_toggle` |
| Dynamic Behavior > Multi-Select Dropdown | `set_value_select_set_and_pills`, `set_value_set_search_filter`, `set_value_dropdown_selected_highlight` |
| Visual States > State 1 (Initial) | `set_value_initial_state` |
| Visual States > State 2 (Sets Selected) | `set_value_select_set_and_pills` |
| Visual States > State 3 (Loading) | `set_value_basic_analysis` |
| Visual States > State 4 (Results Loaded) | `set_value_basic_analysis`, `set_value_summary_stats`, `set_value_top_20_table` |
| Visual States > State 5 (Active Filters) | `set_value_filter_rarity`, `set_value_filters_compose` |
| Visual States > State 6 (Split Active) | `set_value_split_by_rarity`, `set_value_split_by_color`, `set_value_split_by_owned` |
| Visual States > State 7 (No Priced Cards) | `set_value_no_priced_cards_edge_case` |
| Visual States > State 8 (Dropdown Open) | `set_value_select_set_and_pills`, `set_value_set_search_filter` |
| Visual States > State 9 (Multiple Sets) | `set_value_multi_set_comparison` |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 7 | `set_value_initial_state`, `set_value_select_set_and_pills`, `set_value_basic_analysis`, `set_value_summary_stats`, `set_value_top_20_table`, `set_value_filter_rarity`, `set_value_split_by_rarity`, `set_value_multi_set_comparison` |
| Medium | 12 | `set_value_remove_set_pill`, `set_value_top_20_card_link`, `set_value_filter_color`, `set_value_filter_card_type`, `set_value_filter_owned`, `set_value_filter_price_threshold`, `set_value_filters_compose`, `set_value_split_by_color`, `set_value_split_by_owned`, `set_value_chart_bar_click_scryfall`, `set_value_reanalyze_different_source`, `set_value_toggle_price_type_foil`, `set_value_set_search_filter` |
| Low | 5 | `set_value_dropdown_selected_highlight`, `set_value_home_link_navigation`, `set_value_no_priced_cards_edge_case`, `set_value_chart_tooltip_hover`, `set_value_chart_legend_toggle` |

**Total new intents: 24** (0 existing)
