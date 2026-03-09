# Sealed Products Page -- Test Plan

**UX Description:** `tests/ui/ux-descriptions/sealed.md`
**Page:** `/sealed` (`mtg_collector/static/sealed.html`)

---

## 1. Existing Intents

| # | Filename | Summary |
|---|----------|---------|
| 1 | `sealed_add_and_table_view.yaml` | Add a sealed product (Lorwyn Eclipsed Collector Booster Omega Pack) and verify it appears in table view. Covers Flow 12 (add via name search) and Flow 4 (table view). |
| 2 | `sealed_multi_order_aggregation.yaml` | Add the same product twice with different quantities/prices, verify aggregated row shows combined quantity, and detail modal lists both entries separately. Covers aggregation logic and Flow 8 (detail modal). |
| 3 | `sealed_open_modal_navigation.yaml` | Search in the Open Product modal, select a product to see contents preview, click "Back" to return to search, and close the modal. Covers Flow 14 navigation (search, select, back, close). |
| 4 | `sealed_open_no_contents.yaml` | In the Open Product modal, products without contents data appear grayed out with "No contents data" badge and are not clickable; products with contents are selectable. Covers open result item visual states. |
| 5 | `sealed_open_product.yaml` | Full open flow: search for a product with contents, preview card list, confirm open, verify cards added and status bar summary. Covers Flow 14 end-to-end. |

---

## 2. Proposed New Intents

### HIGH Priority

These cover core CRUD operations and primary user flows that are not yet tested.

#### 2.1 `sealed_edit_entry.yaml`

- **Description:** Open the detail modal for a sealed product, expand the edit pane on an entry, modify the quantity and purchase price, save, and verify the updated values appear in the refreshed detail modal.
- **UX Flows/States:** Flow 9 (Edit a Collection Entry), entry edit pane states (collapsed/expanded), detail modal.
- **Testability:** Fully testable. Requires at least one product in the collection (add one first or use fixture data). The save action triggers a PUT and re-fetch, so verification is straightforward via re-opening the detail modal.

#### 2.2 `sealed_dispose_entry.yaml`

- **Description:** Open the detail modal for an owned entry, expand the edit pane, select "sold" from the dispose dropdown, enter a sale price, click "Dispose", and verify the entry now shows "sold" status.
- **UX Flows/States:** Flow 10 (Dispose of a Collection Entry), dispose status transitions (owned -> sold).
- **Testability:** Fully testable. Verify status badge color change and status text in the detail modal or collection view. Requires a product with "owned" status.

#### 2.3 `sealed_delete_entry.yaml`

- **Description:** Open the detail modal, expand the edit pane, click "Delete", confirm the browser dialog, and verify the product disappears from the collection (or the entry count decreases).
- **UX Flows/States:** Flow 11 (Delete a Collection Entry), browser confirmation dialog.
- **Testability:** Limited -- browser `confirm()` dialogs require Playwright's `page.on('dialog')` handling. The harness must accept the dialog. If dialog handling is not supported, this intent cannot be fully automated. Mark as **limited testability**.

#### 2.4 `sealed_add_via_tcgplayer_url.yaml`

- **Description:** Open the Add modal, paste a TCGPlayer URL into the URL input, click "Look Up", verify the add form appears with the resolved product, fill in details, and add to collection.
- **UX Flows/States:** Flow 13 (Add via TCGPlayer URL), TCGPlayer URL lookup states (success).
- **Testability:** Limited -- depends on whether the test fixture includes TCGPlayer product ID mappings in the sealed products catalog. The `/api/sealed/from-tcgplayer` endpoint must be able to resolve the URL/ID against local data. If the fixture lacks this mapping, the lookup will fail. Mark as **limited testability**.

#### 2.5 `sealed_search_collection.yaml`

- **Description:** With multiple products in the collection, type a search query into the search input, verify only matching products appear, clear the search, and verify all products return.
- **UX Flows/States:** Flow 2 (Search Collection), client-side filtering, empty filter state ("No entries match your filters.").
- **Testability:** Fully testable. Requires at least two products with distinct names. Use fixture data or add products as setup.

### MEDIUM Priority

These cover view configuration, filtering, and secondary UI interactions.

#### 2.6 `sealed_grid_view_and_resize.yaml`

- **Description:** Switch to grid view, verify product cards display with images and badges, adjust the grid size slider, and verify cards resize visually.
- **UX Flows/States:** Flow 4 (Switch View Mode -- grid), Flow 6 (Resize Grid Cards), grid card visual states (image, quantity badge, status badge).
- **Testability:** Fully testable. Visual verification via screenshots. Slider interaction requires Playwright range input manipulation.

#### 2.7 `sealed_sidebar_filters.yaml`

- **Description:** Open the filter sidebar, select a category pill (e.g. "Booster Box"), verify the collection filters to show only booster boxes, then click "Clear Filters" and verify all products return.
- **UX Flows/States:** Flow 3 (Filter by Sidebar), category pill interaction, clear filters, sidebar open/close states.
- **Testability:** Fully testable. Requires fixture data with at least two different product categories.

#### 2.8 `sealed_sidebar_set_filter.yaml`

- **Description:** Open the filter sidebar, search for a set in the set filter dropdown, select it to create a pill, verify the collection filters to that set, remove the pill, verify products return.
- **UX Flows/States:** Flow 3 (Filter by Sidebar -- set multi-select), multi-select dropdown behavior, selected pills with remove.
- **Testability:** Fully testable. Requires fixture data with products from at least two different sets.

#### 2.9 `sealed_sort_grid_and_table.yaml`

- **Description:** In table view, click a column header to sort, verify sort direction toggles. Switch to grid view, click a sort button, verify sort order changes.
- **UX Flows/States:** Flow 5 (Sort Products), sort direction indicators (arrows), both view modes.
- **Testability:** Fully testable. Requires at least two products with different values in the sorted column. Verification by checking row/card order in DOM.

#### 2.10 `sealed_column_configuration.yaml`

- **Description:** In table view, click the column config icon, toggle a column off (e.g. "Set"), verify the column disappears from the table, toggle it back on, verify it reappears. Close the drawer.
- **UX Flows/States:** Flow 7 (Configure Table Columns), column drawer open/close, column visibility toggle.
- **Testability:** Fully testable. Column visibility is observable by checking `<th>` elements in the rendered table.

#### 2.11 `sealed_detail_modal_contents.yaml`

- **Description:** Click a product card to open the detail modal, verify all expected sections are present: product info (set, category), cost section, entries list. Verify external links (TCGPlayer, Card Kingdom) appear when available.
- **UX Flows/States:** Flow 8 (View Product Detail), detail modal layout, contents breakdown, links section.
- **Testability:** Fully testable. Content verification via DOM inspection of the detail modal.

#### 2.12 `sealed_status_bar_updates.yaml`

- **Description:** Note the initial stats bar values (entries, items, invested, market value), add a product with a known price, verify the stats bar updates to reflect the new totals.
- **UX Flows/States:** Stats Bar Content Pattern, stats bar updates after mutation.
- **Testability:** Fully testable. Parse the `#status` div text before and after adding a product.

### LOW Priority

These cover edge cases, visual polish, and less common interactions.

#### 2.13 `sealed_empty_collection_state.yaml`

- **Description:** On a fresh instance with no sealed products, verify the empty collection message appears: "No sealed products in your collection yet. Click '+ Add' to get started."
- **UX Flows/States:** Empty collection visual state.
- **Testability:** Limited -- requires a test instance with zero sealed collection entries. If the `--test` fixture pre-loads sealed data, the fixture must be modified or entries deleted first. Mark as **limited testability**.

#### 2.14 `sealed_keyboard_escape_dismiss.yaml`

- **Description:** Open the add modal, press Escape to close it. Open the filter sidebar, press Escape to close it. Open the detail modal, press Escape to close it. Verify the dismissal priority order.
- **UX Flows/States:** Keyboard Shortcuts (Escape key), modal/sidebar/drawer layering.
- **Testability:** Fully testable. Playwright can send `Escape` keypresses and verify visibility state of overlays.

#### 2.15 `sealed_price_status_display.yaml`

- **Description:** Verify the prices status indicator shows a meaningful state (e.g. "Prices: not loaded" or "Prices: today"). Click it to trigger a price fetch. Verify the text changes to "Prices: fetching..." during the request.
- **UX Flows/States:** Flow 15 (Fetch/Refresh Prices), prices status states.
- **Testability:** Limited -- the actual price fetch hits external APIs or requires MTGJSON price data in the fixture. The "fetching..." transient state may be too brief to capture via screenshot. Mark as **limited testability**.

#### 2.16 `sealed_detail_price_history.yaml`

- **Description:** Open the detail modal for a product that has a TCGPlayer product ID, verify the price history section loads and displays a table with Date, Low, Mid, Market, High columns.
- **UX Flows/States:** Detail modal async loading, price history section.
- **Testability:** Limited -- requires price history data in the database for the specific product's `tcgplayer_product_id`. If no price data is loaded, the section remains hidden. Mark as **limited testability**.

#### 2.17 `sealed_sidebar_price_date_filters.yaml`

- **Description:** Open the filter sidebar, enter a minimum price, verify only products above that price appear. Enter a date range, verify filtering by date.
- **UX Flows/States:** Flow 3 (Filter by Sidebar -- price range, date range).
- **Testability:** Fully testable. Requires fixture data with products at different price points and dates.

#### 2.18 `sealed_add_modal_change_product.yaml`

- **Description:** Open the Add modal, search and select a product, verify the add form appears, click "Change" to return to search, select a different product, verify the form updates.
- **UX Flows/States:** Flow 12 (Add via Name Search -- "Change" button), add modal state transitions (searching -> form -> searching -> form).
- **Testability:** Fully testable. Straightforward navigation within the add modal.

#### 2.19 `sealed_open_with_tracking.yaml`

- **Description:** In the Open Product modal, select a product, check the "Add to sealed collection as 'opened'" checkbox, verify purchase price and date fields appear, fill them in, confirm the open.
- **UX Flows/States:** Flow 14 (Open -- tracking option), open-track checkbox toggle, conditional field display.
- **Testability:** Fully testable. Extends `sealed_open_product` by exercising the tracking checkbox and its conditional fields.

#### 2.20 `sealed_dispose_listed_to_owned.yaml`

- **Description:** Dispose an owned entry to "listed" status, then re-open and dispose the listed entry back to "owned", verifying the bidirectional status transition works.
- **UX Flows/States:** Flow 10 (Dispose -- listed -> owned transition), status transition rules.
- **Testability:** Fully testable. Multi-step flow that exercises both directions of the owned/listed transition.

---

## 3. Coverage Matrix

Maps each section of the UX description to the intents that cover it. Existing intents are prefixed with `[E]`, proposed intents with `[P]`.

| UX Section | Intents | Coverage |
|------------|---------|----------|
| **Flow 1: Browse Sealed Collection** | `[E] sealed_add_and_table_view` | Partial -- page load, table render, aggregation basics |
| **Flow 2: Search Collection** | `[P] sealed_search_collection` | Not yet covered |
| **Flow 3: Filter by Sidebar** | `[P] sealed_sidebar_filters`, `[P] sealed_sidebar_set_filter`, `[P] sealed_sidebar_price_date_filters` | Not yet covered |
| **Flow 4: Switch View Mode** | `[E] sealed_add_and_table_view`, `[P] sealed_grid_view_and_resize` | Partial -- table view covered, grid view proposed |
| **Flow 5: Sort Products** | `[P] sealed_sort_grid_and_table` | Not yet covered |
| **Flow 6: Resize Grid Cards** | `[P] sealed_grid_view_and_resize` | Not yet covered |
| **Flow 7: Configure Table Columns** | `[P] sealed_column_configuration` | Not yet covered |
| **Flow 8: View Product Detail** | `[E] sealed_multi_order_aggregation`, `[P] sealed_detail_modal_contents` | Partial -- aggregation detail covered, full detail proposed |
| **Flow 9: Edit a Collection Entry** | `[P] sealed_edit_entry` | Not yet covered |
| **Flow 10: Dispose of a Collection Entry** | `[P] sealed_dispose_entry`, `[P] sealed_dispose_listed_to_owned` | Not yet covered |
| **Flow 11: Delete a Collection Entry** | `[P] sealed_delete_entry` | Not yet covered |
| **Flow 12: Add via Name Search** | `[E] sealed_add_and_table_view`, `[P] sealed_add_modal_change_product` | Partial -- basic add covered, "Change" flow proposed |
| **Flow 13: Add via TCGPlayer URL** | `[P] sealed_add_via_tcgplayer_url` | Not yet covered |
| **Flow 14: Open a Sealed Product** | `[E] sealed_open_modal_navigation`, `[E] sealed_open_no_contents`, `[E] sealed_open_product`, `[P] sealed_open_with_tracking` | Well covered -- navigation, no-contents guard, full open flow. Tracking option proposed. |
| **Flow 15: Fetch/Refresh Prices** | `[P] sealed_price_status_display` | Not yet covered |
| **Navigation** | `[P] sealed_detail_modal_contents` | Not yet covered (external links) |
| **Keyboard Shortcuts** | `[P] sealed_keyboard_escape_dismiss` | Not yet covered |
| **Empty Collection State** | `[P] sealed_empty_collection_state` | Not yet covered |
| **Stats Bar** | `[P] sealed_status_bar_updates` | Not yet covered |
| **Column Drawer** | `[P] sealed_column_configuration` | Not yet covered |
| **Sidebar States** | `[P] sealed_sidebar_filters` | Not yet covered |
| **Grid Card Visual States** | `[P] sealed_grid_view_and_resize` | Not yet covered |
| **Status Badge Colors** | `[P] sealed_dispose_entry` | Not yet covered (implicit via status change) |
| **Prices Status States** | `[P] sealed_price_status_display` | Not yet covered |
| **Detail Modal Async (Price History)** | `[P] sealed_detail_price_history` | Not yet covered |
| **Open Product Preview Async** | `[E] sealed_open_modal_navigation`, `[E] sealed_open_product` | Covered |
| **LocalStorage Persistence** | `[P] sealed_grid_view_and_resize`, `[P] sealed_column_configuration` | Not yet covered (implicit -- would need page reload to verify persistence) |
| **Responsive Behavior (768px)** | -- | Not covered -- out of scope for intent-based tests |

---

## 4. Limited Testability Summary

| Proposed Intent | Limitation | Mitigation |
|-----------------|------------|------------|
| `sealed_delete_entry` | Browser `confirm()` dialog requires special Playwright dialog handling | Use `page.on('dialog', dialog => dialog.accept())` before clicking Delete. If the harness does not support dialog interception, skip or mark xfail. |
| `sealed_add_via_tcgplayer_url` | Depends on TCGPlayer product ID mappings in fixture data | Verify the fixture includes at least one sealed product with `tcgplayer_product_id` set. If not, this test cannot resolve a URL. |
| `sealed_empty_collection_state` | Requires a collection with zero sealed entries | Either use a fresh instance without demo data, or delete all entries as a setup step (expensive and fragile). |
| `sealed_price_status_display` | Price fetch hits external APIs; "fetching..." state is transient | May only be able to verify the initial status text ("not loaded" or similar). The fetching transition may be too fast for screenshot capture. |
| `sealed_detail_price_history` | Requires price history data in the database | Only testable if `fetch-prices` has been run and the fixture includes stored price records. Otherwise the section stays hidden. |
| **LocalStorage persistence** (implicit in multiple intents) | Verifying localStorage persistence requires a page reload within the test | If the harness supports `page.reload()`, add a reload step after setting preferences. Otherwise, persistence is untestable. |
