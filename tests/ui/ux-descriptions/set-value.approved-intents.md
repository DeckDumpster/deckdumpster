# Set Value Analysis -- Approved Intents

Reviewed: 2026-03-09
Existing intents: 0
Proposed new: 24
Result: 7 approved for implementation, 5 deferred, 12 cut

Fixture note: The `--test` fixture has ZERO price data across all sets (0 of
817 cards have prices). This means the chart renders all-zero bins, the top 20
table is empty, median is $0.00, and all tier percentages are 0%. Intents must
be written to account for this: they can verify structural elements (chart
renders, stats row appears, table exists) but cannot verify meaningful price
distributions or populated top-20 rows. The fixture does have 12 owned cards
and 318 special-treatment cards, so the Owned and Card Type filters are
partially exercisable.

---

## Implement Now

- `set_value_initial_state` -- Load `/set-value` and verify: "Set Value Analysis" title, "Search sets..." input, "TCGplayer" toggle active, "Normal" toggle active, Analyze button disabled, empty state message reads "Select one or more sets and click Analyze to view value distribution." Filter bar, chart, summary, and table are all hidden. High value -- validates page load correctness.

- `set_value_select_set_and_analyze` -- Focus the search input, verify dropdown opens. Type a partial name to filter, click a set. Verify a pill appears, Analyze button enables. Click Analyze. Verify loading message appears then disappears, and the filter bar, chart canvas, summary stats row, and top 20 table section all become visible. This merges the proposed `set_value_select_set_and_pills` and `set_value_basic_analysis` into one end-to-end flow, which is how a real user would operate the page.

- `set_value_summary_stats` -- After running an analysis, verify the summary row shows: Total Cards (nonzero), With Prices (can be 0 in fixture), Median, and the four tier percentages (Chaff, Modest, High, Premium). Even with all-zero prices, this verifies the stats row renders and labels are correct. Can assert "Total Cards" > 0 and "With Prices" = 0 for the fixture.

- `set_value_filter_rarity` -- After analysis, deactivate the "C" (Common) pill. Verify the stat-total count decreases (proving the filter took effect). Reactivate it, verify the count returns. This is the single best filter test because rarity distribution exists even without prices -- the "Total Cards" stat changes regardless of price data.

- `set_value_filter_card_type_and_owned` -- After analysis, switch Cards toggle to "Special" and verify Total Cards decreases (fixture has 318 specials out of ~800). Switch Owned toggle to "Owned" and verify Total Cards drops further (fixture has 12 owned). Switch both back to "All" and verify recovery. Merges the proposed `set_value_filter_card_type`, `set_value_filter_owned`, and `set_value_filters_compose` into a single intent that proves all three toggles work and that filters compose.

- `set_value_split_by_rarity` -- After analysis, click "Rarity" in the split toggle. Verify the chart re-renders (chart canvas is visible). This is the highest-value split test because it changes the fundamental chart structure. Without price data the chart bars are all zero, but the legend labels should change from set names to rarity categories, which is screenshot-verifiable.

- `set_value_remove_set_pill` -- Select two sets, verify two pills appear. Click the "x" on one pill, verify it disappears. Remove the second pill, verify Analyze button becomes disabled. Tests the multi-select deselection flow, which has subtle enable/disable logic.

## Deferred

- `set_value_multi_set_comparison` -- Requires two sets selected and analyzed. With zero prices, the visual difference (multiple bar colors) is not discernible in all-zero charts. Defer until price data is available in the fixture.

- `set_value_split_by_color` / `set_value_split_by_owned` -- Same chart with different legend labels. Low incremental value over `set_value_split_by_rarity`. Defer.

- `set_value_reanalyze_different_source` / `set_value_toggle_price_type_foil` -- Switching source or type and re-analyzing. With zero prices, the results are identical either way. Defer until the fixture has price data.

- `set_value_filter_price_threshold` -- Price filtering requires priced cards to produce visible changes. With the current fixture (0 priced), all cards are excluded when the price filter is active. Defer.

## Cut

- `set_value_top_20_table` -- The top 20 table is empty in the fixture (0 priced cards). Cannot verify populated rows. Structural presence is already verified by `set_value_select_set_and_analyze`.
- `set_value_top_20_card_link` -- No rows exist to click. Cannot test.
- `set_value_filter_color` -- Redundant with `set_value_filter_rarity` (same mechanism, different dimension). One filter test proves the pattern works.
- `set_value_chart_bar_click_scryfall` -- Canvas click events are unreliable in screenshot-based testing. Also requires price data for populated bars.
- `set_value_chart_tooltip_hover` -- Canvas hover interactions cannot be tested via screenshot harness.
- `set_value_chart_legend_toggle` -- Canvas legend clicks cannot be reliably automated.
- `set_value_set_search_filter` -- Redundant with search behavior tested in `set_value_select_set_and_analyze`.
- `set_value_dropdown_selected_highlight` -- Minor visual detail (red text on selected set). Low regression risk.
- `set_value_home_link_navigation` -- Trivial navigation link. Zero regression value.
- `set_value_no_priced_cards_edge_case` -- This IS the default fixture state, so it is already implicitly tested by every other intent. No dedicated intent needed.
- `set_value_select_set_and_pills` -- Merged into `set_value_select_set_and_analyze`.
- `set_value_basic_analysis` -- Merged into `set_value_select_set_and_analyze`.
