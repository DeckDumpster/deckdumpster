# Sheets Page -- Approved Intents

## Analysis Notes

Fixture data (test container at localhost:36437):
- 14 sets available, all have at least one product (no empty-product set exists)
- BLB play: 8 sheets, 4 variants, includes foil sheets, guest cards (theList from `spg`), treatments (BL, SC, FA), full-art lands
- BLB collector: 6 sheets, 2 variants, includes foilShowcaseRareMythic with guest cards and EA/SC/BL/FA treatments
- Both `price_sources` enabled (tcg,ck) but no cards have price data populated (all null) -- price badges will show "SF"/"CK" without dollar amounts
- All cards have `printing_id` and `ck_url` so SF/CK badges will render
- camelCase sheet names present (e.g., `rareMythicWithShowcase`, `foilLand`, `foilShowcaseRareMythic`)

## Implement Now

- `sheets_initial_load_and_set_select` -- Navigate to /sheets, confirm the set input transitions from disabled "Loading sets..." to enabled "Search sets...", type a partial name to filter the dropdown, click a result, and verify product radio pills appear with the first auto-selected. Merges proposed intents 1 (initial_load_state) and 2 (set_search_and_select) since they form one continuous flow and the initial state is only interesting as a precondition for set selection.

- `sheets_product_switch_reloads_sheets` -- With BLB selected, confirm the first product (collector) is auto-selected and sheets render. Click the "play" product pill, confirm it highlights red, the URL hash updates to include `product=play`, and sheet content reloads with different sheet names (e.g., "common" appears in play but not in collector). Validates product switching and hash synchronization in one pass.

- `sheets_section_collapse_expand_with_cards` -- After sheets load for BLB play, confirm the Variants section is expanded by default and all sheet sections are collapsed. Click the "common" sheet header to expand it, confirm card images appear in a grid with pull-rate badges below each card. Click the header again to collapse it and confirm cards are hidden. Merges proposed intents 6 (collapse/expand) and 7 (card_grid_and_badges) since expanding a section is the prerequisite for seeing cards, and badge verification is the natural assertion once cards are visible.

- `sheets_card_zoom_overlay` -- Expand a sheet section, click a card image, confirm the zoom overlay appears with a large card image. Click anywhere on the overlay to dismiss it and confirm the overlay disappears. Straightforward interaction with clear visual before/after states.

- `sheets_deep_link_url_hash` -- Navigate directly to /sheets#set=blb&product=play, confirm the set input auto-fills with "Bloomburrow (blb)", the play product radio is selected, and sheet content renders without any manual interaction. Critical for shareability and bookmarking.

- `sheets_variants_table_content` -- After loading BLB play sheets, confirm the Variants section shows a table with probability values and pill-shaped sheet labels for each variant row. Verify status text shows sheet/card counts (e.g., "8 sheets"). Validates the primary data display on the page.

- `sheets_foil_sheet_indicators` -- Load BLB play sheets, confirm foil sheets (e.g., "Foil", "Foil Land") show a foil tag in their section headers. Expand the "Foil" sheet and confirm card wrappers have the `foil` class. Also confirm variant pills for foil sheets use the `.foil-pill` styling. Merges proposed intent 13 (foil_card_treatment) but scoped to class/attribute assertions, not visual CSS effects.

## Deferred

- `sheets_keyboard_navigation_dropdown` -- Keyboard arrow/enter/escape in the set dropdown. Medium-value and the mouse-based selection flow already covers set selection. Keyboard-specific behavior is a nice accessibility test but not a regression priority for the first pass.

- `sheets_grid_column_adjustment` -- Plus/minus column buttons and localStorage persistence. Low regression risk; the controls are simple and isolated. localStorage persistence across reloads adds test complexity for minimal value.

- `sheets_open_pack_navigation` -- Clicking "Open Pack" navigates to /crack with hash params. This is a single-link navigation check. Low risk of regression and the link target (/crack page) is tested by its own intents.

- `sheets_subgroup_headers_and_sorting` -- Verifying subgroup header format (rarity, odds fractions, percentages) and sort order (main set before guest, rarity ordering, weight descending). The exact text formatting and sort order are fragile to assert and low regression risk. The presence of subgroup headers is already implicitly validated by the collapse/expand intent.

- `sheets_url_hash_updates_on_interaction` -- Redundant. Hash updates are already verified in `sheets_product_switch_reloads_sheets` (observes hash change on product switch) and `sheets_deep_link_url_hash` (consumes hash on load).

- `sheets_set_input_clears_on_reopen` -- Clicking the set input after a selection clears it and reopens the full list. Niche interaction, low regression risk.

- `sheets_sheet_name_prettification` -- camelCase to "Title Case With Spaces" conversion. Purely cosmetic text formatting. If it breaks, the page still functions. Low value as a standalone test; partially observed in other intents when section headers are read.

- `sheets_external_price_links` -- SF/CK badge links with target=_blank. Cannot verify external navigation in Playwright without new-tab handling complexity. Badge presence is partially covered by `sheets_section_collapse_expand_with_cards`. No price data in fixture makes this even less interesting.

- `sheets_error_state_display` -- No fixture data triggers an API error (all sets have products, all set/product combos return valid sheets). Would require API mocking or a deliberately broken set, neither of which exists.

- `sheets_no_products_available` -- No set in the fixture returns an empty product list. Cannot be tested without data manipulation.

- `sheets_guest_card_border_color` -- Purple bottom border for guest-set cards. Requires inspecting CSS custom property `--set-color` values, which is fragile. The presence of guest cards is already exercised when viewing sheets that contain them.

- `sheets_header_title_home_link` -- Clicking "Explore Sheets" title navigates to /. Trivial link check, not worth a dedicated scenario.

## Cuts (removed entirely)

None removed entirely -- all proposed intents are accounted for above, either approved (merged where appropriate) or deferred with rationale.
