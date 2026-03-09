# Edit Order Page -- Approved UI Scenario Intents

**Page:** `/edit-order?id=N`
**Date:** 2026-03-09
**Source test plan:** `edit-order.test-plan.md` (13 proposed, 5 approved)

---

## Disposition Summary

| # | Proposed Intent | Verdict | Reason |
|---|----------------|---------|--------|
| 1 | edit_order_load_and_view | KEEP (expanded) | Core smoke test. Absorbs #9 (card row elements). |
| 2 | edit_order_no_id_error | CUT | Trivial JS branch. No real user scenario -- nobody navigates without an ID. Tests a static string, not behavior. |
| 3 | edit_order_save_metadata | KEEP (expanded) | Primary write action. Absorbs #10 (source dropdown). |
| 4 | edit_order_inline_edit_card | KEEP (narrowed) | Limited visual feedback by design, but tests the core inline-edit interaction. |
| 5 | edit_order_remove_card | KEEP | High-value destructive action with confirmation and summary-bar update. |
| 6 | edit_order_replace_card | KEEP | Unique flow: search overlay in replace mode with card swap. |
| 7 | edit_order_search_overlay_close | CUT | Closing a modal is not a user goal. Implicitly tested by any intent that opens the overlay. |
| 8 | edit_order_search_no_results | CUT | Tests a static "No results found" string. Zero user value. |
| 9 | edit_order_card_row_elements | MERGE into #1 | Redundant with load_and_view -- if cards load, their elements are visible. |
| 10 | edit_order_metadata_source_dropdown | MERGE into #3 | The source dropdown is just another metadata field. Fold into save_metadata. |
| 11 | edit_order_empty_card_list | CUT | Requires fixture manipulation. Tests a trivial empty state string. |
| 12 | edit_order_navigation_home_link | CUT | Every page has this. Tested once in the index suite, not per-page. |
| 13 | edit_order_search_overlay_results_grid | CUT | Search overlay is fully exercised by add_card (existing) and replace_card (#6). |

---

## Approved Intents (implement now)

### 1. edit_order_load_and_view

- **Filename:** `edit_order_load_and_view.yaml`
- **Description:** When I open the edit page for an existing order, I see the left panel pre-filled with the order's seller name, order number, date, source, financial totals, and a "Save Order Details" button. In the right panel I see a summary bar with the card count and total value, a "+ Add Card" button, and a list of card rows -- each showing a thumbnail, card name, set and collector number, a condition dropdown, a finish dropdown, a price input, and replace/remove action buttons.
- **Covers:** Flow 1, State 4, card row element inventory
- **Priority:** P0 -- gate all other edit-order tests on this

### 2. edit_order_save_metadata

- **Filename:** `edit_order_save_metadata.yaml`
- **Description:** On the edit order page, I change the seller name, pick a different source from the dropdown (verifying TCGPlayer, Card Kingdom, and Other are available), update the shipping cost, then click "Save Order Details". The button briefly shows "Saving..." and disables, then a green "Saved" confirmation appears below it. After the confirmation disappears, I reload the page and confirm the changes persisted.
- **Covers:** Flow 2, States 6-7, source dropdown options, save persistence
- **Priority:** P0

### 3. edit_order_inline_edit_card

- **Filename:** `edit_order_inline_edit_card.yaml`
- **Description:** On the edit order page, I change a card's condition dropdown to "Lightly Played" and its finish dropdown to "foil". I then reload the page and verify both values persisted, confirming the auto-save on change worked without any explicit save button.
- **Covers:** Flow 3
- **Priority:** P1

### 4. edit_order_remove_card

- **Filename:** `edit_order_remove_card.yaml`
- **Description:** On the edit order page, I note the current card count in the summary bar, then click the remove button on one of the cards and accept the confirmation dialog. The card disappears from the list and the summary bar updates to show one fewer card.
- **Covers:** Flow 6, State 14, summary bar recalculation
- **Priority:** P1

### 5. edit_order_replace_card

- **Filename:** `edit_order_replace_card.yaml`
- **Description:** On the edit order page, I note a card's name, then click its replace button. The search overlay opens with the input focused. I search for a different card, select one from the results, and the overlay closes. The card list refreshes and the original card name is gone, replaced by the one I selected.
- **Covers:** Flow 5, search overlay in replace mode
- **Priority:** P1

---

## Deferred (do not implement now)

None deferred -- the remaining 8 proposed intents were cut outright or merged. The existing `edit_order_add_card` intent (referenced in the test plan but not yet written) covers Flow 4 and the search overlay in add mode. That intent plus these 5 give complete coverage of every user-facing flow on this page.

---

## Final Coverage

| UX Flow | Intent |
|---------|--------|
| Flow 1: Load and View | `edit_order_load_and_view` |
| Flow 2: Edit Metadata | `edit_order_save_metadata` |
| Flow 3: Inline Edit Card | `edit_order_inline_edit_card` |
| Flow 4: Add Card | `edit_order_add_card` (to be written separately) |
| Flow 5: Replace Card | `edit_order_replace_card` |
| Flow 6: Remove Card | `edit_order_remove_card` |
| Flow 7: Close Search | covered implicitly by add/replace flows |
| Flow 8: No Order ID | cut (no user value) |

**Total: 5 new intents + 1 existing = 6 intents covering all 6 user-facing flows.**
