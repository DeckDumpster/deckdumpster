# Binders Page — Approved Intents

## Existing Intents (No Changes)

These four intents already exist and cover cross-page binder interactions. They are not re-reviewed here but are referenced for coverage overlap.

- `binders_create_and_manage` — Create a binder, see it in the list, open it, add cards. Covers the happy path end-to-end. (E1)
- `binders_manage_from_card_modal` — Assign a card to a binder from the collection card modal. (E2, collection page)
- `collection_deck_binder_filter` — Filter collection by container assignment. (E3, collection page)
- `decks_exclusivity_enforcement` — Move a card between deck and binder via card modal. (E4, collection page)

---

## Implement Now

### 1. `binders_list_view_populated`

**Description:** When I navigate to /binders, I see the two existing binders ("Trade Binder" and "Foil Collection") rendered as a card grid. Each binder card displays the name, card count (6 each), and any metadata that was set (color, binder type badge). Clicking a binder card takes me to its detail view.

**Rationale:** The list view is the landing state for the binders page. E1 creates a binder and views the list, but does not verify that pre-existing binders render with all their metadata fields. This validates the core read path.

**From test plan:** Merges #2 (binders_list_view_card_grid) and absorbs #5 (binders_detail_view_metadata) navigation aspect. The click-to-detail transition is folded in because the list view is useless without verifying you can enter a binder.

---

### 2. `binders_create_with_all_fields`

**Description:** From the binders list view, I click "New Binder" and the modal opens with title "New Binder" and all fields empty. I fill in the name ("Rare Binder"), description ("High-value rares"), color ("red"), binder type ("4-Pocket"), and storage location ("top shelf"). I click Save. The modal closes and I land on the detail view for the newly created binder. The detail view shows all five metadata fields I entered.

**Rationale:** E1 covers the basic create-then-add-cards flow but does not exercise all optional fields or verify they round-trip to the detail view. This is the most important CRUD operation on the page.

**From test plan:** Refines #3 (binders_create_new_binder). The description is now concrete about which values to enter and what to verify, making it deterministic for implementation.

---

### 3. `binders_edit_binder`

**Description:** From a binder's detail view (e.g., "Trade Binder"), I click "Edit" and the modal opens with title "Edit Binder" and fields pre-populated with the current data (name "Trade Binder", color "blue", type "9-Pocket"). I change the name to "Updated Trade Binder" and the color to "green", then click Save. The modal closes and the detail view updates in-place to show the new name and color without navigating away.

**Rationale:** Edit is a core CRUD operation. The pre-population check is the key regression signal -- if the modal opens blank during an edit, data loss occurs.

**From test plan:** Unchanged from #7 (binders_edit_binder), made more concrete with specific field values.

---

### 4. `binders_delete_returns_to_list`

**Description:** From a binder's detail view, I click "Delete Binder". After accepting the confirmation dialog, I am returned to the list view. The deleted binder no longer appears in the binder grid.

**Rationale:** Delete is the remaining CRUD operation. The confirm() dialog is handled by Playwright's `page.on('dialog')` handler -- this is standard and testable. The key assertion is that the binder disappears from the list.

**From test plan:** Merges #8 (binders_delete_binder). Drops #9 (binders_delete_preserves_cards) -- see Deferred section.

---

### 5. `binders_add_cards_full_flow`

**Description:** From the "Trade Binder" detail view, I click "Add Cards". The modal opens showing "Type to search your collection..." I type "pr" into the search field and see matching cards from my collection appear (e.g., "Preacher of the Schism"). I click a card to select it (it highlights). I click "Add Selected". The modal closes, the binder's card count increases from 6 to 7, and the newly added card appears in the card table.

**Rationale:** This is the most complex user flow on the page. E1 covers add-cards at a high level, but this intent specifically validates the search-select-confirm picker UX, the visual selection feedback, and the post-mutation data refresh. The search term "pr" is chosen because "Preacher of the Schism" is an unassigned card in the test fixture.

**From test plan:** Merges #10 (binders_add_cards_search_flow) and #11 (binders_add_cards_select_and_confirm). These were artificially split -- the search flow is meaningless without the confirm step, and the confirm step requires the search flow. One intent, one coherent user journey.

---

### 6. `binders_remove_cards`

**Description:** From a binder's detail view with cards present, I check one card using its per-row checkbox, then click "Remove Selected". The card disappears from the table and the binder's card count decreases by 1.

**Rationale:** Remove is the counterpart to add. This tests the checkbox selection mechanism, the remove API call, and the post-mutation refresh. Checking a single card is sufficient -- select-all is deferred.

**From test plan:** Unchanged from #13 (binders_remove_cards), made slightly more concrete.

---

### 7. `binders_detail_view_empty_card_list`

**Description:** After creating a new binder (via the "New Binder" modal), I land on its detail view. Since it has no cards, the card table displays a single row with the message "No cards in this binder". The header shows "Add Cards" and "Remove Selected" buttons.

**Rationale:** Empty states are a common source of visual bugs (missing messages, broken layouts). This also validates that create redirects to detail, which is a distinct behavior from clicking a list card.

**From test plan:** Unchanged from #6 (binders_detail_view_empty_card_list). Folded in header control visibility check since we are already on the detail view.

---

## Deferred

### `binders_empty_state` (test plan #1)

**Rationale for deferral:** Requires a fresh database with zero binders. The test container ships with 2 pre-loaded binders. Testing empty state would require either (a) deleting both binders first (fragile multi-step setup) or (b) a dedicated fixture. The empty state is trivial HTML -- a static div with `display:none` toggled by JS. Low regression risk.

---

### `binders_create_name_required_validation` (test plan #4)

**Rationale for deferral:** The validation fires via `alert()`, which is a browser-native dialog. Playwright can intercept it, but Claude Vision cannot see it. The only visually verifiable assertion is "the modal stays open," which is a weak signal. The validation itself is a single `if (!name)` check that is unlikely to regress independently.

---

### `binders_delete_preserves_cards` (test plan #9)

**Rationale for deferral:** This is a server-side behavior test (binder_id set to NULL on delete). Verifying it requires navigating to the collection page, searching for a card, and confirming it still exists -- a cross-page journey that is better tested via API integration tests or the existing `decks_delete_keeps_cards` intent pattern. The binders page itself cannot observe whether deleted cards persist in the collection.

---

### `binders_add_cards_no_results` (test plan #12)

**Rationale for deferral:** Searching for a nonexistent card and seeing "No matching cards found" tests a single conditional render branch. The message is static text. Extremely low regression risk. If the search mechanism itself breaks, `binders_add_cards_full_flow` will catch it.

---

### `binders_remove_no_selection_alert` (test plan #14)

**Rationale for deferral:** Same problem as name validation -- fires `alert()`, invisible to Claude Vision. The only verifiable assertion is "no cards were removed," which is the default state. Zero regression value.

---

### `binders_select_all_toggle` (test plan #15)

**Rationale for deferral:** Select-all is a convenience feature. The checkbox toggle mechanism is standard HTML. The real risk (incorrect card IDs in the remove request) is not visually testable. If select-all breaks, the remove flow still works with individual checkboxes (covered by `binders_remove_cards`).

---

### `binders_back_to_list_navigation` (test plan #16)

**Rationale for deferral:** Already implicitly covered by `binders_delete_returns_to_list` (which returns to the list view after delete) and `binders_list_view_populated` (which verifies the list view renders). Testing the "Back to Binders" button in isolation adds no regression value beyond verifying a single `onclick="showList()"` handler.

---

### `binders_modal_backdrop_close` (test plan #17)

**Rationale for deferral:** Backdrop click-to-close is a generic modal behavior shared across the entire app. Testing it on the binders page specifically provides no unique coverage. The event listener is 3 lines of code. If it breaks, it breaks everywhere and would be caught by any modal-using intent.

---

### `binders_card_table_columns` (test plan #18)

**Rationale for deferral:** Column headers are static HTML in the `<thead>`. They cannot change without a code edit to `binders.html`. The `binders_add_cards_full_flow` and `binders_remove_cards` intents will screenshot the card table with data present -- Claude Vision will see the columns as part of those screenshots. No standalone intent needed.

---

### `binders_header_breadcrumb_navigation` (test plan #19)

**Rationale for deferral:** The breadcrumb is a single `<a href="/">MTG</a>` tag. Testing that an anchor tag navigates to its href is testing the browser, not the application. Zero regression value.

---

### `binders_exclusivity_conflict` (test plan #20)

**Rationale for deferral:** The conflict alert fires via `alert()` (invisible to Claude Vision). Setting up the test requires all copies of a card to already be assigned -- which means either (a) knowing the exact fixture state deeply or (b) multi-step setup to assign cards elsewhere first. The exclusivity enforcement is already covered by E4 (`decks_exclusivity_enforcement`) from the card modal side. Server-side 409 logic is better validated via API tests.

---

### `binders_detail_view_metadata` (test plan #5)

**Rationale for deferral:** Absorbed into `binders_list_view_populated` (which clicks into detail view) and `binders_create_with_all_fields` (which verifies metadata on the detail view after create). A standalone "view metadata" intent is redundant when both the list-to-detail navigation and the create flow already land on the detail view and verify its contents.

---

## Coverage Summary

| UX Flow | Covered By |
|---------|------------|
| Flow 1: View All Binders (populated) | `binders_list_view_populated` |
| Flow 1: View All Binders (empty) | Deferred |
| Flow 2: Create a New Binder | `binders_create_with_all_fields`, `binders_detail_view_empty_card_list`, **E1** |
| Flow 3: View Binder Details | `binders_list_view_populated`, `binders_create_with_all_fields` |
| Flow 4: Edit a Binder | `binders_edit_binder` |
| Flow 5: Delete a Binder | `binders_delete_returns_to_list` |
| Flow 6: Add Cards to a Binder | `binders_add_cards_full_flow`, **E1** |
| Flow 7: Remove Cards from a Binder | `binders_remove_cards` |
| Flow 8: Select/Deselect All | Deferred |
| Flow 9: Return to List View | Implicitly covered by `binders_delete_returns_to_list` |
| Flow 10: Close Modal via Backdrop | Deferred |
| Navigation: Breadcrumb | Deferred |
| Card Table Columns | Implicitly covered by card-present screenshots |
| Cross-page: Card modal binder assignment | **E2** |
| Cross-page: Collection filter by container | **E3** |
| Cross-page: Deck/binder exclusivity | **E4** |

**Total: 7 new intents to implement** (down from 20 proposed). All 10 UX flows have at least partial coverage.
