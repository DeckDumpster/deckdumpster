# Collection Page -- Approved Intents

Reviewed: 2026-03-09

## Review Summary

The test plan proposed 50 new intents on top of 13 existing ones (11 `collection_*` + 2 `views_*`). That is excessive. The collection page is already the most-tested page in the app. Many proposed intents duplicate coverage that exists on the standalone card detail page, test trivial variations of already-covered mechanics, or target features that are untestable with the fixture data.

**Existing collection-page intents (13, all kept):**
- `collection_add_from_modal`
- `collection_add_second_card_no_refresh`
- `collection_card_modal_detail`
- `collection_deck_binder_filter`
- `collection_filter_rarity`
- `collection_inline_deck_creation`
- `collection_modal_close`
- `collection_multiselect_new_deck`
- `collection_orders_view`
- `collection_price_chart`
- `collection_view_toggle`
- `views_container_only_filter`
- `views_save_and_load`

---

## Approved: Implement Now (7 new intents)

These fill genuine coverage gaps for high-traffic, high-risk user journeys that no existing intent touches.

### 1. `collection_search_debounced`
- **Description**: Type a card name into the search input, verify the collection re-fetches and shows only matching cards. Clear the search to restore the full view. Status text updates.
- **Justification**: Search is the single most-used feature on the page. No existing intent tests it. Server-side fetch path is distinct from client-side filtering (which `collection_filter_rarity` covers).
- **Fixture data**: 43 cards with distinct names; searching "crawler" or a partial name will narrow results.

### 2. `collection_filter_color`
- **Description**: Open the filter sidebar, select one or more color pills (W/U/B/R/G/C). Collection re-renders to show only matching cards. Deselect to restore.
- **Justification**: Color is the second most common filter dimension after rarity. Tests client-side AND filtering, a different code path than rarity checkboxes. Fixture has good color distribution (W:6, U:10, B:9, R:8, G:12, C:7).
- **Note**: Keep this instead of `collection_filter_type` -- color pills use a different UI pattern (pill toggles vs checkboxes) and the AND logic is more complex. One additional client-side filter beyond rarity is sufficient.

### 3. `collection_sort_table_columns`
- **Description**: In table view, click a column header to sort. Click again to reverse. Arrow indicator shows sort state.
- **Justification**: Sorting is a core browsing operation with zero existing coverage. Tests a code path completely orthogonal to filtering.
- **Fixture data**: 43 cards with varied names, sets, CMC -- sorting will produce visibly different orderings.

### 4. `collection_multiselect_delete`
- **Description**: Enter multi-select mode, select cards, click Delete, confirm dialog, cards removed.
- **Justification**: Destructive bulk operation with no existing coverage. `collection_multiselect_new_deck` covers the multi-select-then-assign path; this covers the multi-select-then-delete path, which is the highest-risk bulk action (data loss if broken).
- **Fixture data**: 14 unassigned cards available for deletion without side effects.

### 5. `collection_multiselect_toggle`
- **Description**: Open More menu, click "Toggle Multi-Select". Selection bar appears with "0 selected". Checkboxes appear on cards. Select cards, count updates. Toggle off, bar hides, selections clear.
- **Justification**: The existing `collection_multiselect_new_deck` jumps straight into multi-select without testing the toggle mechanics, the selection bar UI, or the count display. This tests the multi-select lifecycle itself.
- **Note**: This can be merged with `collection_multiselect_select_all_none` -- the test should also click "All" and "None" within the same scenario, since those are trivial button clicks in the same bar.

### 6. `collection_sidebar_open_close`
- **Description**: Click "Filters" button, sidebar slides in. Verify 13 filter dimensions are present. Click "Close Filters" or backdrop to close.
- **Justification**: The sidebar is the gateway to all filtering. `collection_filter_rarity` opens it as a side effect but never tests the open/close mechanics or verifies the sidebar structure. This is a structural assertion, not a behavioral one -- it catches regressions where filter dimensions disappear.
- **Note**: Do NOT separately test `collection_clear_filters` -- clearing filters is already part of `collection_filter_rarity` and `collection_filter_color`. The clear button is just one click; no separate intent needed.

### 7. `collection_wishlist_panel`
- **Description**: Open More menu, click "Wishlist (N)", panel slides in showing wanted cards. Remove an entry via X. Close panel via backdrop.
- **Justification**: Wishlist panel is a major feature with no collection-page coverage. The fixture data includes 3 wishlist entries, so the panel will have content. Tests a completely different UI surface (slide-in panel) from anything else covered.
- **Fixture data**: 3 wishlist entries (Bonny Pall, Disruptor Flute, Niko).

---

## Approved: Implement Later / Defer (5 intents)

These are valid but lower priority. Implement after the first 7 are stable.

### 8. `collection_modal_filterable_click` (defer)
- **Description**: Open card modal, click a filterable element (set name), modal closes, filter applied.
- **Justification**: Filterable click is a unique interaction pattern with complex propagation logic. But it is medium-risk -- if it breaks, users can still filter manually.

### 9. `collection_grid_sort_bar` (defer)
- **Description**: In grid view, sort bar with sort buttons. Click to sort, click again to reverse.
- **Justification**: Valid complement to `collection_sort_table_columns`, but lower priority since grid sort uses the same underlying sort logic. Only the UI entry point differs.

### 10. `collection_column_config` (defer)
- **Description**: In table view, click grid icon to open column config drawer. Toggle columns on/off.
- **Justification**: Column configuration is a power-user feature. The drawer UI is unique and worth testing eventually, but not high-risk.

### 11. `collection_save_view` (defer)
- **Description**: Apply filters, click "Save Current Filters as View", enter name, verify view appears in dropdown.
- **Justification**: `views_save_and_load` and `views_container_only_filter` test *loading* saved views. This would test *creating* them. Valid gap, but the create path is simpler than the load path.

### 12. `collection_grid_column_resize` (defer)
- **Description**: In grid view, use +/- buttons to change column count.
- **Justification**: Simple UI control, low risk, but tests a code path nothing else covers.

---

## Cut: Do Not Implement (38 intents)

### Redundant with card detail page intents (7 cut)

The standalone card detail page (`/card/:set/:cn`) already has intents for these exact operations. The collection modal shares the same API endpoints and nearly identical UI. Testing the same operation twice on two pages is waste.

| Proposed Intent | Already Covered By |
|---|---|
| `collection_modal_dfc_flip` | `card_detail_dfc_flip` |
| `collection_modal_want_button` | `card_detail_want_toggle` |
| `collection_modal_copy_deck_assignment` | `card_detail_deck_assign` |
| `collection_modal_delete_copy` | `card_detail_delete_copy` |
| `collection_modal_dispose_copy` | `card_detail_dispose_copy` |
| `collection_modal_receive_ordered` | `card_detail_receive_copy` |
| `collection_modal_copy_binder_assignment` | `binders_manage_from_card_modal` |

### Redundant with existing collection intents (6 cut)

| Proposed Intent | Why Redundant |
|---|---|
| `collection_modal_escape_close` | `collection_modal_close` already tests closing. Escape is just a keyboard shortcut for the same action. Not worth a separate Claude Vision API call. |
| `collection_modal_backdrop_close` | Same -- `collection_modal_close` covers modal closing. Backdrop click vs X button is the same outcome. |
| `collection_clear_filters` | Already embedded in `collection_filter_rarity` (clears filters at end). Adding `collection_filter_color` will also clear. |
| `collection_status_text_updates` | Status text is visible in screenshots for `collection_filter_rarity`, `collection_search_debounced`, and others. Not a standalone testable behavior -- it is an assertion within other tests. |
| `collection_multiselect_select_all_none` | Merged into `collection_multiselect_toggle` (approved above). |
| `collection_modal_full_page_link` | `card_detail_from_collection_modal` already navigates from collection modal to the standalone page, which implicitly tests this link. |

### Too many filter dimension variants (8 cut)

One client-side filter test (`collection_filter_rarity` existing + `collection_filter_color` new) is sufficient to prove the filtering infrastructure works. Individual filter dimensions use the same `applyFilters()` code path. Testing each dimension separately has diminishing returns.

| Cut Intent | Reason |
|---|---|
| `collection_filter_type` | Same filter infrastructure as color/rarity. |
| `collection_filter_set` | Same infrastructure, plus autocomplete -- but autocomplete is secondary. |
| `collection_filter_finish` | Same infrastructure. |
| `collection_filter_treatment` | Same infrastructure + limited testability (fixture may lack treatment cards). |
| `collection_filter_cmc_range` | Same infrastructure (range inputs). |
| `collection_filter_price_range` | Same infrastructure + no price data in fixture. |
| `collection_filter_date_range` | Same infrastructure (range inputs). |
| `collection_filter_subtype` | Same infrastructure + autocomplete. |
| `collection_filter_cn_range` | Same infrastructure (range inputs). |
| `collection_filter_status_disposition` | Limited testability (no sold/traded cards in fixture). |

### Untestable or fixture-limited (7 cut)

| Cut Intent | Reason |
|---|---|
| `collection_include_unowned_cycle` | Requires unowned cards for a filtered set. Complex multi-state cycle. No existing DFC cards in fixture for flip testing either. Limited value relative to cost. |
| `collection_buy_missing_cards` | Clipboard copy and external tab open are explicitly untestable in headless browser. |
| `collection_multiselect_share` | URL shortening depends on external service. Clipboard untestable. |
| `collection_virtual_scroll_grid` | Performance/DOM count assertion is not possible with screenshot-based tests. |
| `collection_empty_state` | Requires empty collection. Fixture has 43 cards. Would need custom fixture. |
| `collection_wishlist_copy_for_vendor` | Clipboard and external tab untestable. |
| `collection_ordered_banner` | Fixture does have 5 ordered cards, but the banner logic depends on whether the ordered banner is visible at page load -- unclear if it triggers with only 5 of 43 cards ordered. Low-confidence test. |

### Low-value / trivial (10 cut)

| Cut Intent | Reason |
|---|---|
| `collection_header_home_link` | Clicking "Collection" heading to go home is trivially simple. If the link breaks, every other nav test catches it. |
| `collection_image_display_toggle` | Crop vs Contain is a visual subtlety. Claude Vision would struggle to distinguish crop vs contain rendering. Not reliably assertable. |
| `collection_price_floor_setting` | No price data in fixture. Even with prices, the status text value change would be subtle. |
| `collection_multiselect_want` | Bulk want is a minor feature. Single-card want is already covered by `card_detail_want_toggle`. |
| `collection_multiselect_add_to_binder` | Structurally identical to `collection_multiselect_new_deck` (existing) -- just targeting binder instead of deck. Same modal pattern. |
| `collection_multiselect_shift_select` | Shift-click range selection is a keyboard+mouse combo that is hard to verify visually. The count update is the same as regular select. |
| `collection_table_filterable_click` | Filterable click in table is the same mechanism as in modal (deferred). Testing it separately adds nothing. |
| `collection_inline_binder_creation` | `collection_inline_deck_creation` already tests the inline creation pattern for decks. Binder is the same UI with a different dropdown. |
| `collection_modal_move_between_containers` | Niche power-user operation. Deck/binder assignment is already covered. Move is just remove+add. |
| `collection_wishlist_clear_all` | "Clear All" is a single button click on the wishlist panel. `collection_wishlist_panel` (approved) already tests the panel. Adding a clear-all click within that test is sufficient. |
| `collection_orders_receive_all` | Niche operation, limited testability, ordered cards feature already covered by `card_detail_receive_copy`. |

---

## Final Tally

| Category | Count |
|---|---|
| Existing (kept) | 13 |
| Approved: Implement Now | 7 |
| Approved: Defer | 5 |
| Cut | 38 |
| **Total after implementation** | **20** (eventually 25 with deferred) |

This brings collection-page coverage from 13 to 20 intents -- a 54% increase -- while keeping the test suite maintainable and each new intent justifiable by the gap it fills.
