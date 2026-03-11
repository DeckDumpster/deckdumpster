# Explore Sheets -- Test Plan

Source UX description: `tests/ui/ux-descriptions/sheets.md`
Route: `/sheets`

---

## Existing Coverage

No existing intents cover the Explore Sheets page. All proposed intents below are new.

---

## Proposed Intents

### 1. sheets_initial_load_state

- **Filename**: `sheets_initial_load_state`
- **Description**: When I navigate to `/sheets`, I see the set input disabled with placeholder "Loading sets...", then it becomes enabled with placeholder "Search sets..." after sets load. The status area shows the number of sets loaded. The content area displays "Select a set and product to explore booster sheets". The Open Pack button is disabled.
- **Reference**: Section 2 (Navigation), Section 3 (Header Controls -- set input, status, pack button), Section 5 (On Page Load), Section 7 (Initial Load State, Sets Loaded No Selection)
- **Testability**: Fully testable with Playwright. Navigate to `/sheets`, wait for load, assert placeholder text transitions, status text, empty state message, and button disabled state.
- **Priority**: high

---

### 2. sheets_set_search_and_select

- **Filename**: `sheets_set_search_and_select`
- **Description**: I can click the set search input to open the dropdown showing all available sets. When I type a partial set name, the dropdown filters in real time. I can click a set in the dropdown to select it. The input updates to show the set name and code, the dropdown closes, and product radio pills appear.
- **Reference**: Section 3 (set input, set dropdown), Section 4 Flow 1 (Browse Sheets steps 4-9), Section 5 (On Set Selection), Section 7 (Set Dropdown Open, Set Selected)
- **Testability**: Fully testable. Focus input, assert dropdown opens, type filter text, assert filtered results, click a result, assert input value and product radios appear.
- **Priority**: high

---

### 3. sheets_keyboard_navigation_dropdown

- **Filename**: `sheets_keyboard_navigation_dropdown`
- **Description**: When I focus the set input and the dropdown opens, I can use ArrowDown and ArrowUp to move the active highlight through the set list. The highlighted item scrolls into view. Pressing Enter selects the highlighted set and closes the dropdown. Pressing Escape closes the dropdown and blurs the input.
- **Reference**: Section 3 (set dropdown keyboard navigation), Section 4 Flow 7 (Keyboard Navigation)
- **Testability**: Fully testable. Focus input, send ArrowDown key events, assert `.active` class moves, send Enter, assert selection. Separately test Escape dismissal.
- **Priority**: medium

---

### 4. sheets_product_radio_selection

- **Filename**: `sheets_product_radio_selection`
- **Description**: After I select a set, product radio pills appear with the first product auto-selected. I can click a different product pill to switch products. The selected pill highlights with a red background. Sheets reload with the new product data and the URL hash updates.
- **Reference**: Section 3 (product radio buttons), Section 4 Flow 2 (Switch Product), Section 5 (On Product Change)
- **Testability**: Fully testable. Select a set, assert first product is checked, click a different radio, assert it becomes checked, assert URL hash changes, assert content reloads.
- **Priority**: high

---

### 5. sheets_variants_section_display

- **Filename**: `sheets_variants_section_display`
- **Description**: After sheets load, the Variants section is expanded by default showing a table with columns for variant number, probability, and contents. Each variant row shows pill-shaped labels for each sheet it pulls from. The status area shows the total sheet and card counts.
- **Reference**: Section 3 (section header), Section 4 Flow 1 (step 13), Section 5 (Collapsible Sections, Variant Pills), Section 7 (Sheets Loaded)
- **Testability**: Fully testable. Select set and product, wait for sheets to load, assert Variants section has class `open`, assert table headers and row content, assert status text format "N sheets, M cards".
- **Priority**: high

---

### 6. sheets_section_collapse_expand

- **Filename**: `sheets_section_collapse_expand`
- **Description**: I can click a sheet section header to expand it, revealing the card grid with subgroup headers. Clicking the same header again collapses it. The arrow indicator rotates when expanded and points right when collapsed. Sheet sections start collapsed while the Variants section starts expanded.
- **Reference**: Section 3 (section header, collapsible sections), Section 4 Flow 3 (Explore Sheet Contents steps 1-2), Section 5 (Collapsible Sections), Section 7 (Sheet Section Expanded)
- **Testability**: Fully testable. Assert sheet sections lack `open` class initially, click a section header, assert `open` class added, assert body visible, click again, assert collapsed.
- **Priority**: high

---

### 7. sheets_card_grid_and_badges

- **Filename**: `sheets_card_grid_and_badges`
- **Description**: When I expand a sheet section, I see cards displayed in a grid. Each card shows an image with rarity-colored top border. Below each card, badges display the pull rate percentage. Treatment badges (BL, SC, EA, FA) appear for cards with special treatments. Price link badges (SF, CK) appear based on settings.
- **Reference**: Section 3 (card image, badges), Section 5 (Card Badges, Card Border Colors), Section 7 (Sheet Section Expanded)
- **Testability**: Fully testable. Expand a sheet section, assert card elements exist with `.sheet-card` class, assert `.badge.pull-rate` badges present, assert border gradient CSS custom properties set. Treatment and price badges depend on card data and settings -- testable if fixture data includes treated/priced cards.
- **Priority**: high

---

### 8. sheets_card_zoom_overlay

- **Filename**: `sheets_card_zoom_overlay`
- **Description**: When I click a card image in the sheet grid, a full-screen zoom overlay appears with an enlarged version of the card. I can click anywhere on the overlay to dismiss it and return to the normal view.
- **Reference**: Section 3 (zoom overlay, zoom image), Section 4 Flow 3 (steps 5-6), Section 5 (Zoom Overlay), Section 7 (Zoom Overlay Active)
- **Testability**: Fully testable. Expand a sheet, click a `.sheet-card`, assert `#zoom-overlay` has class `active`, assert `#zoom-img` src is set, click the overlay, assert `active` class removed.
- **Priority**: high

---

### 9. sheets_grid_column_adjustment

- **Filename**: `sheets_grid_column_adjustment`
- **Description**: I can click the plus button to increase the card grid column count and the minus button to decrease it. The column count display updates accordingly. The plus button disables at 12 columns and the minus button disables at 1 column. The preference persists across page reloads via localStorage.
- **Reference**: Section 3 (column minus/plus buttons, column count display), Section 4 Flow 4 (Adjust Grid Columns), Section 5 (Card Grid Column Count)
- **Testability**: Fully testable. Click plus/minus buttons, assert `#col-count` text changes, assert CSS custom property `--grid-cols` updates, assert button disabled states at boundaries. localStorage persistence testable by reloading page and checking restored value.
- **Priority**: medium

---

### 10. sheets_open_pack_navigation

- **Filename**: `sheets_open_pack_navigation`
- **Description**: When I have a set and product selected, the Open Pack button becomes enabled. Clicking it navigates me to `/crack` with the current set and product pre-selected via URL hash parameters.
- **Reference**: Section 2 (Open Pack button), Section 3 (Open Pack button), Section 4 Flow 5 (Navigate to Pack Opening)
- **Testability**: Fully testable. Select set and product, assert `#pack-btn` is not disabled, click it, assert navigation to `/crack#set=...&product=...`.
- **Priority**: medium

---

### 11. sheets_deep_link_url_hash

- **Filename**: `sheets_deep_link_url_hash`
- **Description**: When I navigate directly to `/sheets#set=blb&product=play`, the page auto-selects the specified set in the input, loads and auto-selects the specified product, and renders the sheets without any manual interaction.
- **Reference**: Section 4 Flow 6 (Deep Link via URL Hash), Section 5 (On Page Load -- hash parsing), Section 7 (Deep-Linked State)
- **Testability**: Fully testable. Navigate to `/sheets#set=<valid_set>&product=<valid_product>`, wait for load, assert set input shows the set name, assert correct product radio is checked, assert sheet content is rendered.
- **Priority**: high

---

### 12. sheets_subgroup_headers_and_sorting

- **Filename**: `sheets_subgroup_headers_and_sorting`
- **Description**: When I expand a sheet section, cards are organized into subgroups by set, rarity, and weight. Each subgroup header shows the rarity name, group odds as a fraction and percentage, and per-card odds. Main set cards appear before guest set cards, and within each set, groups sort by rarity order then by weight descending.
- **Reference**: Section 5 (Subgroup Headers)
- **Testability**: Fully testable. Expand a sheet section, assert subgroup header elements exist with rarity text and odds format. Sorting order verifiable by reading sequential subgroup headers and comparing rarity/weight values.
- **Priority**: medium

---

### 13. sheets_foil_card_treatment

- **Filename**: `sheets_foil_card_treatment`
- **Description**: When I view a foil sheet, cards with the foil property display a rainbow gradient overlay and an animated light streak effect. The card wrapper has the `foil` class applied. Foil sheets are also indicated in section headers and variant pills use distinct foil pill styling.
- **Reference**: Section 5 (Foil Visual Treatment, Variant Pills -- foil pill)
- **Testability**: Partially testable. Can assert `.foil` class on `.sheet-card-img-wrap`, and `.foil-pill` class on variant pills. Visual gradient/animation effects are CSS-only and not directly assertable via Playwright DOM checks, but class presence confirms they would render.
- **Priority**: medium

---

### 14. sheets_header_title_home_link

- **Filename**: `sheets_header_title_home_link`
- **Description**: The "Explore Sheets" title in the page header is a link. When I click it, I am navigated to the homepage at `/`.
- **Reference**: Section 2 (Navigation -- header link)
- **Testability**: Fully testable. Assert `h1 a` element with href `/`, click it, assert navigation to homepage.
- **Priority**: low

---

### 15. sheets_url_hash_updates_on_interaction

- **Filename**: `sheets_url_hash_updates_on_interaction`
- **Description**: When I select a set and product, the URL hash updates to `#set={code}&product={product}`. When I switch to a different product, the hash updates accordingly. This allows me to copy the URL and share or bookmark the current view.
- **Reference**: Section 4 Flow 1 (step 12), Section 4 Flow 2 (step 3), Section 5 (On Product Change -- updateHash)
- **Testability**: Fully testable. Select set, assert hash contains set code. Select product, assert hash contains product. Switch product, assert hash updates.
- **Priority**: medium

---

### 16. sheets_set_input_clears_on_reopen

- **Filename**: `sheets_set_input_clears_on_reopen`
- **Description**: When I have a set selected and I click the set input again, the input text clears and the full set list reappears in the dropdown, allowing me to search for and select a different set.
- **Reference**: Section 4 Flow 1 (step 4)
- **Testability**: Fully testable. Select a set, then click the input again, assert input value is empty, assert dropdown shows full list.
- **Priority**: medium

---

### 17. sheets_sheet_name_prettification

- **Filename**: `sheets_sheet_name_prettification`
- **Description**: When sheets load, camelCase sheet names from the API (like "rareMythicWithShowcase") are displayed as space-separated title case ("Rare Mythic With Showcase") in section headers and variant pills.
- **Reference**: Section 5 (Sheet Name Prettification)
- **Testability**: Fully testable. Load sheets for a set that has camelCase sheet names, assert section header text contains properly formatted names (spaces, title case) rather than camelCase.
- **Priority**: low

---

### 18. sheets_external_price_links

- **Filename**: `sheets_external_price_links`
- **Description**: When I expand a sheet section, each card may show Scryfall (SF) and Card Kingdom (CK) badge links depending on the price_sources setting. These are anchor tags that open in new tabs and optionally display the card's price.
- **Reference**: Section 2 (Scryfall badge, Card Kingdom badge), Section 3 (Scryfall link badge, Card Kingdom link badge), Section 5 (Card Badges)
- **Testability**: Limited testability. Can assert badge `<a>` elements exist with correct `href` patterns and `target="_blank"`. Cannot verify external page loads. Badge visibility depends on `price_sources` setting and card data having `printing_id`/`ck_url`.
- **Priority**: low

---

### 19. sheets_error_state_display

- **Filename**: `sheets_error_state_display`
- **Description**: When the sheets API returns an error (e.g., missing booster data for a set/product combination), the content area displays the error message in an italic, centered, gray style. The status text is cleared.
- **Reference**: Section 7 (Error State)
- **Testability**: Limited testability. Requires a set/product combination that triggers an API error. If the test fixture includes a set without booster data, the error path can be exercised. Otherwise, would need API mocking which is not available.
- **Priority**: low

---

### 20. sheets_no_products_available

- **Filename**: `sheets_no_products_available`
- **Description**: When I select a set that has no available products, no radio buttons appear, the Open Pack button stays disabled, and no sheets are loaded.
- **Reference**: Section 7 (No Products Available)
- **Testability**: Limited testability. Requires a set in the fixture database that returns an empty product list from `/api/products`. If no such set exists in the test fixture, this scenario cannot be exercised without data manipulation.
- **Priority**: low

---

### 21. sheets_guest_card_border_color

- **Filename**: `sheets_guest_card_border_color`
- **Description**: When I expand a sheet section containing "guest" cards from a different set (e.g., The List or bonus sheet cards), those cards display a purple bottom border gradient, distinguishing them from main-set cards which have a dark bottom border.
- **Reference**: Section 5 (Card Border Colors -- set gradient)
- **Testability**: Partially testable. Can assert `--set-color` CSS custom property on card elements. Requires sheet data that includes cards from a different set code than the selected set.
- **Priority**: low

---

## Coverage Matrix

| UX Section | Intents Covering It |
|---|---|
| 2. Navigation -- header link | sheets_header_title_home_link |
| 2. Navigation -- Open Pack button | sheets_open_pack_navigation |
| 2. Navigation -- Scryfall/CK badges | sheets_external_price_links, sheets_card_grid_and_badges |
| 3. Header -- set input | sheets_initial_load_state, sheets_set_search_and_select, sheets_set_input_clears_on_reopen |
| 3. Header -- set dropdown | sheets_set_search_and_select, sheets_keyboard_navigation_dropdown |
| 3. Header -- product radios | sheets_product_radio_selection |
| 3. Header -- Open Pack button | sheets_open_pack_navigation, sheets_initial_load_state |
| 3. Header -- column controls | sheets_grid_column_adjustment |
| 3. Header -- status text | sheets_initial_load_state, sheets_variants_section_display |
| 3. Content -- section headers | sheets_section_collapse_expand, sheets_variants_section_display |
| 3. Content -- card images | sheets_card_grid_and_badges, sheets_card_zoom_overlay |
| 3. Content -- zoom overlay | sheets_card_zoom_overlay |
| 3. Content -- badges | sheets_card_grid_and_badges, sheets_external_price_links |
| 4. Flow 1 -- Browse Sheets | sheets_set_search_and_select, sheets_variants_section_display |
| 4. Flow 2 -- Switch Product | sheets_product_radio_selection |
| 4. Flow 3 -- Explore Sheet Contents | sheets_section_collapse_expand, sheets_card_grid_and_badges, sheets_card_zoom_overlay |
| 4. Flow 4 -- Adjust Grid Columns | sheets_grid_column_adjustment |
| 4. Flow 5 -- Navigate to Pack Opening | sheets_open_pack_navigation |
| 4. Flow 6 -- Deep Link | sheets_deep_link_url_hash |
| 4. Flow 7 -- Keyboard Navigation | sheets_keyboard_navigation_dropdown |
| 5. On Page Load | sheets_initial_load_state, sheets_deep_link_url_hash |
| 5. On Set Selection | sheets_set_search_and_select |
| 5. On Product Change | sheets_product_radio_selection, sheets_url_hash_updates_on_interaction |
| 5. Collapsible Sections | sheets_section_collapse_expand |
| 5. Card Grid Column Count | sheets_grid_column_adjustment |
| 5. Zoom Overlay | sheets_card_zoom_overlay |
| 5. Card Badges | sheets_card_grid_and_badges, sheets_external_price_links |
| 5. Foil Visual Treatment | sheets_foil_card_treatment |
| 5. Card Border Colors | sheets_card_grid_and_badges, sheets_guest_card_border_color |
| 5. Sheet Name Prettification | sheets_sheet_name_prettification |
| 5. Variant Pills | sheets_variants_section_display, sheets_foil_card_treatment |
| 5. Subgroup Headers | sheets_subgroup_headers_and_sorting |
| 7. Initial Load State | sheets_initial_load_state |
| 7. Sets Loaded No Selection | sheets_initial_load_state |
| 7. Set Dropdown Open | sheets_set_search_and_select |
| 7. Set Selected Products Loading | sheets_set_search_and_select |
| 7. Sheets Loading | sheets_set_search_and_select |
| 7. Sheets Loaded | sheets_variants_section_display |
| 7. Sheet Section Expanded | sheets_section_collapse_expand, sheets_card_grid_and_badges |
| 7. Zoom Overlay Active | sheets_card_zoom_overlay |
| 7. Error State | sheets_error_state_display |
| 7. No Products Available | sheets_no_products_available |
| 7. Deep-Linked State | sheets_deep_link_url_hash |

---

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| high | 8 | sheets_initial_load_state, sheets_set_search_and_select, sheets_product_radio_selection, sheets_variants_section_display, sheets_section_collapse_expand, sheets_card_grid_and_badges, sheets_card_zoom_overlay, sheets_deep_link_url_hash |
| medium | 7 | sheets_keyboard_navigation_dropdown, sheets_grid_column_adjustment, sheets_open_pack_navigation, sheets_subgroup_headers_and_sorting, sheets_foil_card_treatment, sheets_url_hash_updates_on_interaction, sheets_set_input_clears_on_reopen |
| low | 6 | sheets_header_title_home_link, sheets_sheet_name_prettification, sheets_external_price_links, sheets_error_state_display, sheets_no_products_available, sheets_guest_card_border_color |
