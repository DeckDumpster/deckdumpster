# Sealed Products Page -- Approved Intents

**Reviewed:** 2026-03-09
**Existing intents:** 5
**Proposed in test plan:** 20 (2.1 through 2.20)
**Approved new:** 4
**Deferred:** 5
**Cut:** 11

---

## Existing Intents (5) -- KEEP ALL

All five existing intents are well-scoped, non-overlapping, and cover the two most
complex features on the page (add-to-collection and open-product).

| # | Intent | Covers |
|---|--------|--------|
| 1 | `sealed_add_and_table_view` | Flow 12 (add via name search), Flow 4 (table view) |
| 2 | `sealed_multi_order_aggregation` | Aggregation logic, Flow 8 (detail modal entries list) |
| 3 | `sealed_open_modal_navigation` | Flow 14 navigation (search, select, back, close) |
| 4 | `sealed_open_no_contents` | Open modal guard state (grayed products, badge) |
| 5 | `sealed_open_product` | Flow 14 end-to-end (open, preview, confirm, cards added) |

---

## Approved New Intents (4) -- IMPLEMENT NOW

### 1. `sealed_edit_entry` (was 2.1)

**Description:** Open the detail modal for a product in the collection, click "Edit" on
an entry to expand the edit pane, change the quantity and purchase price, click "Save",
and verify the updated values appear when the detail modal refreshes.

**Why approved:** Edit is a core CRUD operation. The existing 5 intents cover create (add)
and read (detail modal, table view) but have zero coverage of update. This is the single
biggest gap in the sealed test suite.

**Fixture data:** Any of the 8 demo entries work. Use the Duskmourn Collector Booster Box
(id=1, price=$105) -- change quantity from 1 to 2 and price from 105 to 99.

**Flows covered:** Flow 9 (Edit a Collection Entry), entry edit pane collapsed/expanded states.

---

### 2. `sealed_dispose_entry` (was 2.2)

**Description:** Open the detail modal for an owned entry, expand the edit pane, select
"sold" from the dispose dropdown, enter a sale price, click "Dispose", and verify the
entry status changes to "sold".

**Why approved:** Dispose is the other core mutation path alongside edit. The fixture has
6 owned entries to work with. Status transitions are the primary lifecycle mechanism for
sealed products and are currently untested.

**Fixture data:** Use any "owned" entry. Dispose to "sold" with a sale price.

**Flows covered:** Flow 10 (Dispose of a Collection Entry), status badge color change
(owned green -> sold dark-green).

---

### 3. `sealed_delete_entry` (was 2.3)

**Description:** Open the detail modal, expand an entry's edit pane, click "Delete",
confirm the browser dialog, and verify the entry is removed (product disappears from
collection or entry count decreases in the detail modal).

**Why approved:** Completes CRUD coverage (create/read/update/delete). The test plan
flagged this as "limited testability" due to `confirm()` dialogs, but the harness
already auto-accepts dialogs (verified in `test_scenarios.py` lines 120-126 and
`harness.py` line 297). No testability issue.

**Fixture data:** Use a single-entry product so deletion removes the entire row, making
verification unambiguous. The Outlaws of Thunder Junction Bundle (id=5, qty=1) or
Duskmourn Bundle (id=6, qty=1) work well.

**Flows covered:** Flow 11 (Delete a Collection Entry), browser confirmation dialog.

---

### 4. `sealed_search_and_filter` (merged from 2.5, 2.7, 2.8)

**Description:** With the demo collection loaded (8 entries across 5 sets, 3 categories,
3 statuses), type "Bloomburrow" into the search input and verify only Bloomburrow products
appear. Clear the search. Then open the filter sidebar, select the "Booster Pack" category
pill, verify only booster packs appear, click "Clear Filters", and verify all products
return.

**Why approved:** Search and filter are the primary browse mechanisms and have zero
coverage. Merging search + category filter into one intent is efficient because they
exercise the same rendering pipeline and the combined flow is short (type, verify, clear,
open sidebar, click pill, verify, clear).

**Why merged:** The test plan proposed three separate intents (2.5 search, 2.7 category
filter, 2.8 set filter). The set filter (multi-select dropdown with pills) is
mechanically complex and adds little coverage over category filtering -- both funnel
through the same `refilterAndRender()` pipeline. One intent covering search + category
is sufficient. Set filter can be deferred.

**Fixture data:** Search "Bloomburrow" matches 2 products (Collector Booster Box, Collector
Booster Pack). Category "Booster Pack" matches 3 entries (Foundations, MH3, Bloomburrow
packs). Enough diversity to verify filtering works.

**Flows covered:** Flow 2 (Search Collection), Flow 3 (Filter by Sidebar -- category pills),
sidebar open/close, Clear Filters button.

---

## Deferred Intents (5) -- IMPLEMENT LATER

These are real gaps but lower priority than the CRUD operations above.

| # | Proposed | Reason to Defer |
|---|----------|-----------------|
| 2.6 | `sealed_grid_view_and_resize` | Grid is the alternate view. Table view is already covered. Defer until grid-specific bugs surface. |
| 2.9 | `sealed_sort_grid_and_table` | Sort is visual-order verification which is tedious for the vision agent. Low bug surface. |
| 2.10 | `sealed_column_configuration` | Column drawer is niche UI. Low regression risk. |
| 2.14 | `sealed_keyboard_escape_dismiss` | Escape key is a convenience shortcut. Modals have explicit close buttons already tested. |
| 2.19 | `sealed_open_with_tracking` | Extends the well-covered open flow with one checkbox toggle. Small marginal coverage gain. |

---

## Cut Intents (11) -- DO NOT IMPLEMENT

### Redundant with approved or existing intents

| # | Proposed | Why Cut |
|---|----------|---------|
| 2.8 | `sealed_sidebar_set_filter` | Merged into `sealed_search_and_filter`. Set multi-select exercises the same filter pipeline as category pills. |
| 2.11 | `sealed_detail_modal_contents` | Redundant with `sealed_multi_order_aggregation` (existing #2), which already opens the detail modal and verifies entries. Adding another "open modal and check sections" intent is low incremental value. |
| 2.12 | `sealed_status_bar_updates` | The stats bar is implicitly verified by `sealed_add_and_table_view` (existing #1) -- after adding a product, the table view screenshot captures the stats bar. Not worth a dedicated intent. |
| 2.18 | `sealed_add_modal_change_product` | Tiny UX path (click "Change" in the add modal). Already partially covered by the add flow in existing #1. The "Change" button just returns to search -- trivial navigation, not a regression risk. |
| 2.20 | `sealed_dispose_listed_to_owned` | Multi-step dispose chain. `sealed_dispose_entry` already covers the dispose mechanism. Bidirectional transitions are a data-model concern better tested with a unit test, not a UI scenario. |

### Untestable or fragile with fixture data

| # | Proposed | Why Cut |
|---|----------|---------|
| 2.4 | `sealed_add_via_tcgplayer_url` | TCGPlayer URL lookup works in the fixture (verified: product ID `557244` resolves), but the UX flow is nearly identical to the name-search add flow (existing #1). The only unique element is pasting a URL and clicking "Look Up" -- not enough marginal coverage to justify a separate intent. |
| 2.13 | `sealed_empty_collection_state` | Requires zero sealed entries. The test fixture pre-loads 8 entries. Deleting all 8 as setup is fragile and expensive. A unit test or manual check suffices. |
| 2.15 | `sealed_price_status_display` | Price fetch hits external APIs or requires price data the fixture lacks. The "fetching..." state is transient (sub-second). The prices-status endpoint returns `available: false` in the test fixture. Nothing meaningful to verify. |
| 2.16 | `sealed_detail_price_history` | Requires stored price history records. The fixture has none (`prices-status` returns `available: false`, `product_count: 0`). The price history section will remain hidden -- nothing to test. |
| 2.17 | `sealed_sidebar_price_date_filters` | Price range filter works but adds minimal coverage over category filter (both go through `refilterAndRender()`). Date filter is untestable because all fixture entries have `purchase_date: null`. |

---

## Final Intent Roster (9 total)

| # | Intent | Status | Priority |
|---|--------|--------|----------|
| 1 | `sealed_add_and_table_view` | Existing | -- |
| 2 | `sealed_multi_order_aggregation` | Existing | -- |
| 3 | `sealed_open_modal_navigation` | Existing | -- |
| 4 | `sealed_open_no_contents` | Existing | -- |
| 5 | `sealed_open_product` | Existing | -- |
| 6 | `sealed_edit_entry` | **New** | P1 |
| 7 | `sealed_dispose_entry` | **New** | P1 |
| 8 | `sealed_delete_entry` | **New** | P1 |
| 9 | `sealed_search_and_filter` | **New** | P2 |

This brings sealed page coverage to: add, read (table + detail + aggregation), edit,
dispose, delete, search, category filter, and the full open-product flow (navigation,
no-contents guard, end-to-end open). The remaining gaps (grid view, sort, column config,
escape key, price features) are low-risk and can be added if regressions appear.
