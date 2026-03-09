# Binders Page Test Plan

**Page:** `/binders`
**UX Description:** `tests/ui/ux-descriptions/binders.md`

---

## Existing Intents

| # | Filename | Description | UX Sections Covered |
|---|----------|-------------|---------------------|
| E1 | `binders_create_and_manage.yaml` | EXISTING -- Create a binder, see it in the list, open it, add cards to it | Flows 1, 2, 3, 6 |
| E2 | `binders_manage_from_card_modal.yaml` | EXISTING -- Assign an unassigned card to a binder from the card detail modal | (collection page, not binders page) |
| E3 | `collection_deck_binder_filter.yaml` | EXISTING -- Filter collection by deck/binder assignment | (collection page, not binders page) |
| E4 | `decks_exclusivity_enforcement.yaml` | EXISTING -- Move a card between deck and binder via card modal | (collection page, cross-cutting exclusivity) |

---

## Proposed New Intents

### 1. binders_empty_state

- **Filename:** `binders_empty_state.yaml`
- **Description:** I navigate to /binders on a fresh collection with no binders. I should see the empty state message "No binders yet. Click 'New Binder' to create one." and the "New Binder" button in the header.
- **Reference:** Flow 1 (step 4), Visual States -- List View (Empty state)
- **Testability:** full
- **Priority:** medium

### 2. binders_list_view_card_grid

- **Filename:** `binders_list_view_card_grid.yaml`
- **Description:** I navigate to /binders and see my binders rendered as a card grid. Each binder card shows the name, binder type badge, color, storage location, description, card count, and total value.
- **Reference:** Flow 1 (steps 3, 5), Visual States -- List View (Populated), Section 3 -- Binder Cards (List View Grid)
- **Testability:** full
- **Priority:** high

### 3. binders_create_new_binder

- **Filename:** `binders_create_new_binder.yaml`
- **Description:** I click "New Binder", fill in the name and optional fields (description, color, binder type, storage location), and click Save. The modal closes and I am taken to the detail view for the newly created binder with the correct metadata displayed.
- **Reference:** Flow 2, Section 3 -- Create/Edit Binder Modal, Visual States -- Modal States (Create modal)
- **Testability:** full
- **Priority:** high
- **Note:** Overlaps with E1 but provides more focused coverage of the create flow specifically, including all optional fields and the modal state.

### 4. binders_create_name_required_validation

- **Filename:** `binders_create_name_required_validation.yaml`
- **Description:** I click "New Binder", leave the name field empty, and click Save. A browser alert fires saying "Name is required" and the modal stays open.
- **Reference:** Flow 2 (step 5), Error/Alert States
- **Testability:** limited (browser alert() cannot be visually verified by Claude Vision; modal staying open can be)
- **Priority:** medium

### 5. binders_detail_view_metadata

- **Filename:** `binders_detail_view_metadata.yaml`
- **Description:** I click on a binder card in the list view and see the detail view with binder metadata (name, color, type, location, notes, card count, total value), the correct header controls (Back to Binders, Add Cards, Remove Selected), and the Edit and Delete buttons.
- **Reference:** Flow 3, Section 3 -- Header Controls (Detail View), Section 3 -- Detail View Actions, Visual States -- Detail View
- **Testability:** full
- **Priority:** high

### 6. binders_detail_view_empty_card_list

- **Filename:** `binders_detail_view_empty_card_list.yaml`
- **Description:** I create a new binder and view its detail page. Since it has no cards, the card table shows a single row with "No cards in this binder".
- **Reference:** Flow 3 (step 6), Visual States -- Detail View (Binder with no cards)
- **Testability:** full
- **Priority:** medium

### 7. binders_edit_binder

- **Filename:** `binders_edit_binder.yaml`
- **Description:** From a binder's detail view, I click "Edit" and the modal opens with title "Edit Binder" and fields pre-populated with the current binder data. I change the name and color, click Save, and the detail view updates to show the new values without leaving the detail view.
- **Reference:** Flow 4, Section 3 -- Create/Edit Binder Modal, Visual States -- Modal States (Edit modal), Dynamic Behavior -- Modal System
- **Testability:** full
- **Priority:** high

### 8. binders_delete_binder

- **Filename:** `binders_delete_binder.yaml`
- **Description:** From a binder's detail view, I click "Delete Binder". After confirming the browser dialog, the binder is deleted and I am returned to the list view. The deleted binder no longer appears in the binder grid.
- **Reference:** Flow 5, Error/Alert States (confirm dialog)
- **Testability:** limited (confirm() dialog cannot be visually verified; the return to list view and absence of the binder can be)
- **Priority:** high

### 9. binders_delete_preserves_cards

- **Filename:** `binders_delete_preserves_cards.yaml`
- **Description:** I have a binder with cards in it. After deleting the binder, I go to the collection page and search for one of those cards. It should still exist in my collection as an unassigned card.
- **Reference:** Flow 5 (step 5 -- "Cards that were in the binder have their binder_id set to NULL but remain in the collection")
- **Testability:** full
- **Priority:** high

### 10. binders_add_cards_search_flow

- **Filename:** `binders_add_cards_search_flow.yaml`
- **Description:** From a binder's detail view, I click "Add Cards" and see the modal with the initial "Type to search your collection..." message. I type fewer than 2 characters and see "Type at least 2 characters...". I then type a valid search term and see matching cards from my collection with name, set code, collector number, finish, and quantity.
- **Reference:** Flow 6 (steps 1-7), Section 3 -- Add Cards Modal, Visual States -- Modal States (Add Cards modal states)
- **Testability:** full
- **Priority:** high

### 11. binders_add_cards_select_and_confirm

- **Filename:** `binders_add_cards_select_and_confirm.yaml`
- **Description:** From the Add Cards modal with search results showing, I click cards to select them (they highlight), then click "Add Selected". The modal closes, the binder's card count increases, and the newly added cards appear in the card table.
- **Reference:** Flow 6 (steps 8-15), Dynamic Behavior -- Picker Search, Dynamic Behavior -- Data Refresh After Mutations
- **Testability:** full
- **Priority:** high
- **Note:** Partially overlaps with E1 but provides dedicated coverage of the picker selection UX and post-add data refresh.

### 12. binders_add_cards_no_results

- **Filename:** `binders_add_cards_no_results.yaml`
- **Description:** From the Add Cards modal, I search for a card name that does not exist in my collection and see the "No matching cards found" message.
- **Reference:** Flow 6 (step 7), Visual States -- Modal States (Add Cards modal -- no results)
- **Testability:** full
- **Priority:** low

### 13. binders_remove_cards

- **Filename:** `binders_remove_cards.yaml`
- **Description:** From a binder's detail view with cards present, I check one or more cards using the per-row checkboxes and click "Remove Selected". The selected cards disappear from the card table and the binder's card count decreases.
- **Reference:** Flow 7, Dynamic Behavior -- Data Refresh After Mutations
- **Testability:** full
- **Priority:** high

### 14. binders_remove_no_selection_alert

- **Filename:** `binders_remove_no_selection_alert.yaml`
- **Description:** From a binder's detail view, I click "Remove Selected" without checking any cards. A browser alert fires saying "No cards selected".
- **Reference:** Flow 7 (step 3), Error/Alert States
- **Testability:** limited (browser alert() cannot be visually verified; can verify no cards were removed)
- **Priority:** low

### 15. binders_select_all_toggle

- **Filename:** `binders_select_all_toggle.yaml`
- **Description:** From a binder's detail view with multiple cards, I click the select-all checkbox in the table header. All card rows show checked checkboxes. I click select-all again and all checkboxes are unchecked.
- **Reference:** Flow 8, Section 3 -- Card Table
- **Testability:** full
- **Priority:** medium

### 16. binders_back_to_list_navigation

- **Filename:** `binders_back_to_list_navigation.yaml`
- **Description:** From a binder's detail view, I click "Back to Binders". The list view reappears with the binder grid and the header controls switch back to showing only the "New Binder" button.
- **Reference:** Flow 9, Section 2 -- Navigation, Dynamic Behavior -- View Switching, Visual States -- Header Control Visibility
- **Testability:** full
- **Priority:** medium

### 17. binders_modal_backdrop_close

- **Filename:** `binders_modal_backdrop_close.yaml`
- **Description:** I open the "New Binder" modal, then click outside the modal content on the dark backdrop. The modal closes without creating a binder.
- **Reference:** Flow 10, Dynamic Behavior -- Modal System
- **Testability:** full
- **Priority:** low

### 18. binders_card_table_columns

- **Filename:** `binders_card_table_columns.yaml`
- **Description:** From a binder's detail view with cards present, I verify the card table displays all expected columns: a checkbox column, Name, Set (code + collector number), Mana, Type, Finish, and Condition.
- **Reference:** Section 3 -- Card Table
- **Testability:** full
- **Priority:** medium

### 19. binders_header_breadcrumb_navigation

- **Filename:** `binders_header_breadcrumb_navigation.yaml`
- **Description:** On the binders page, I see the breadcrumb "MTG / Binders" in the header. I click the "MTG" link and am navigated to the homepage.
- **Reference:** Section 2 -- Navigation
- **Testability:** full
- **Priority:** low

### 20. binders_exclusivity_conflict

- **Filename:** `binders_exclusivity_conflict.yaml`
- **Description:** I try to add a card to a binder when all copies of that card are already assigned to a deck or another binder. The system shows an alert indicating no unassigned copies are available.
- **Reference:** Flow 6 (steps 11-12), Error/Alert States, Data Dependencies (deck/binder exclusivity)
- **Testability:** limited (browser alert() cannot be visually verified; can verify no cards were added to the binder)
- **Priority:** medium

---

## Coverage Matrix

| UX Section | Covered By |
|------------|------------|
| Flow 1: View All Binders (empty) | binders_empty_state |
| Flow 1: View All Binders (populated) | binders_list_view_card_grid |
| Flow 2: Create a New Binder | binders_create_new_binder, binders_create_name_required_validation, **E1** |
| Flow 3: View Binder Details | binders_detail_view_metadata, binders_detail_view_empty_card_list |
| Flow 4: Edit a Binder | binders_edit_binder |
| Flow 5: Delete a Binder | binders_delete_binder, binders_delete_preserves_cards |
| Flow 6: Add Cards to a Binder | binders_add_cards_search_flow, binders_add_cards_select_and_confirm, binders_add_cards_no_results, binders_exclusivity_conflict, **E1** |
| Flow 7: Remove Cards from a Binder | binders_remove_cards, binders_remove_no_selection_alert |
| Flow 8: Select/Deselect All Cards | binders_select_all_toggle |
| Flow 9: Return to List View | binders_back_to_list_navigation |
| Flow 10: Close Modal via Backdrop | binders_modal_backdrop_close |
| Navigation -- Breadcrumb | binders_header_breadcrumb_navigation |
| Card Table columns | binders_card_table_columns |
| Header Control Visibility | binders_detail_view_metadata, binders_back_to_list_navigation |
| Modal System | binders_create_new_binder, binders_edit_binder, binders_modal_backdrop_close |
| Cross-page: Card modal binder assignment | **E2** (binders_manage_from_card_modal) |
| Cross-page: Collection filter by container | **E3** (collection_deck_binder_filter) |
| Cross-page: Deck/binder exclusivity | **E4** (decks_exclusivity_enforcement) |

---

## Priority Summary

| Priority | Count | Intents |
|----------|-------|---------|
| **high** | 9 | binders_list_view_card_grid, binders_create_new_binder, binders_detail_view_metadata, binders_edit_binder, binders_delete_binder, binders_delete_preserves_cards, binders_add_cards_search_flow, binders_add_cards_select_and_confirm, binders_remove_cards |
| **medium** | 6 | binders_empty_state, binders_create_name_required_validation, binders_detail_view_empty_card_list, binders_select_all_toggle, binders_back_to_list_navigation, binders_exclusivity_conflict |
| **low** | 4 | binders_add_cards_no_results, binders_remove_no_selection_alert, binders_modal_backdrop_close, binders_header_breadcrumb_navigation |
| **EXISTING** | 4 | E1, E2, E3, E4 |
