# Deck Detail Page -- Test Plan

**UX Description:** `tests/ui/ux-descriptions/deck-detail.md`
**Date:** 2026-03-09

---

## 1. Existing Intents

### Deck Detail page-specific intents (`deck_detail_*`)

| Intent File | Summary |
|---|---|
| `deck_detail_direct_navigation.yaml` | Navigate to `/decks/:id`, verify deck name, metadata, zone tabs with counts, card table columns, and dynamic page title. Covers **Flow 1** (page load) and **State 4** (loaded with cards). |
| `deck_detail_card_links_to_card_page.yaml` | Click a card name in the deck card table and verify navigation to `/card/:set/:cn`. Covers **Flow 1** card name links and the **Card Name Links** dynamic behavior. |
| `deck_detail_delete_redirects_to_list.yaml` | Click "Delete Deck", confirm the dialog, verify redirect to `/decks` and deck is gone. Covers **Flow 9** (delete deck) and **State 17** (confirm dialog). |

### Navigation intents (deck list / deck creation -> detail)

| Intent File | Summary |
|---|---|
| `deck_create_redirects_to_detail.yaml` | Create a deck from `/decks`, verify redirect to `/decks/:id` with correct name and empty card table. Covers **Flow 1** partially and **State 6** (no cards). |
| `deck_list_links_to_standalone_detail.yaml` | Click a deck card on `/decks` and verify navigation to the standalone detail page. Covers **Navigation** (decks list -> detail). |

### Broader deck workflow intents (`decks_*`)

| Intent File | Summary |
|---|---|
| `decks_create_and_add_cards.yaml` | Create a deck, add cards to it, verify they appear. Covers **Flow 5** (add cards) partially -- exercises the add-cards flow but was written against the legacy inline view, not the standalone page. |
| `decks_delete_keeps_cards.yaml` | Delete a deck, verify its cards remain in the collection. Covers **Flow 9** (delete) side effect on collection data. |
| `decks_exclusivity_enforcement.yaml` | Move a card between deck and binder via card modal, verify mutual exclusivity. Covers the `deck_id`/`binder_id` exclusivity constraint, not a deck detail page flow directly. |
| `decks_import_expected_and_completeness.yaml` | Import an expected list for Bolt Tribal, verify completeness section shows present/missing breakdown. Covers **Flow 6** (import expected) and **Flow 7** (view completeness) and **State 9** (full tracking). |
| `decks_import_moxfield_decklist.yaml` | Import a text decklist via CSV Import page. Not a deck detail page flow -- covers the CSV import page. |
| `decks_manage_from_card_modal.yaml` | Assign an unassigned card to a deck from the card detail modal. Not a deck detail page flow -- covers the card modal. |
| `decks_precon_origin_metadata.yaml` | Create a precon deck with origin fields, verify metadata display. Covers **Flow 4** (edit modal, precon fields) and **State 11** (edit modal) partially. |
| `decks_reassemble_unassigned_cards.yaml` | Import expected list, verify missing card with "Unassigned" tag, reassemble it, verify it moves to "Present". Covers **Flow 8** (reassemble) and **State 9** (completeness tracking). |

---

## 2. Proposed New Intents

### High Priority

These cover core user flows on the deck detail page that have no dedicated test.

#### 2a. `deck_detail_zone_tab_switching.yaml`

- **Description:** Switch between Mainboard, Sideboard, and Commander zone tabs. Verify that the active tab changes, card table updates to show only cards in the selected zone, zone tab counts remain accurate, and an empty zone shows "No cards in this zone".
- **Priority:** High
- **UX Flows/States Covered:** Flow 2 (switch between zones), State 4 (loaded with cards), State 5 (empty zone).
- **Testability Notes:** Requires a deck with cards in at least two zones (mainboard + sideboard or commander). Demo data's Bolt Tribal may only have mainboard cards -- fixture data needs verification. The empty zone message is straightforward to verify visually.

#### 2b. `deck_detail_select_and_remove_cards.yaml`

- **Description:** Select individual cards and the "Select All" checkbox in the card table, then click "Remove Selected" to remove them from the deck. Verify the cards disappear from the table, zone tab counts update, and the deck card count in the metadata decreases. Verify the cards are unassigned (not deleted from collection).
- **Priority:** High
- **UX Flows/States Covered:** Flow 3 (select and remove cards), State 4 (before removal), State 5 or 6 (after removal if zone/deck becomes empty).
- **Testability Notes:** Fully testable. Requires clicking checkboxes and verifying table re-render. Could verify unassignment by checking collection page afterward. The "no cards selected" alert path (clicking Remove with nothing selected) is lower priority.

#### 2c. `deck_detail_edit_properties.yaml`

- **Description:** Open the Edit modal, change the deck name and format, save, and verify the header updates to reflect the new name and format. Close the modal and confirm no residual overlay.
- **Priority:** High
- **UX Flows/States Covered:** Flow 4 (edit deck properties), State 11 (edit modal open), Flow 10 (close modal).
- **Testability Notes:** Fully testable. The edit modal pre-population can be verified visually. Saving and seeing the header update is the key assertion.

#### 2d. `deck_detail_add_cards_from_collection.yaml`

- **Description:** Open the "Add Cards" modal, search for a card by name, select a result, choose a zone, and click "Add Selected". Verify the modal closes, the card appears in the card table under the correct zone, and zone tab counts update.
- **Priority:** High
- **UX Flows/States Covered:** Flow 5 (add cards from collection), State 12 (add cards modal initial), State 13 (searching with results).
- **Testability Notes:** Requires unassigned cards in the collection that match a search query. Demo data should have unassigned cards. The picker search fires on every keystroke (no debounce), which is fine for testing. The "no unassigned copies" alert path is an edge case for a separate test.

### Medium Priority

These cover secondary flows, edge cases, and visual states.

#### 2e. `deck_detail_completeness_toggle.yaml`

- **Description:** After importing an expected list, verify the completeness section is visible and expanded. Click the completeness header to collapse it, verify only the summary line is visible and the toggle arrow changes direction. Click again to expand. Verify the body reappears.
- **Priority:** Medium
- **UX Flows/States Covered:** State 9 (completeness full tracking), State 10 (completeness collapsed), Dynamic Behavior: Completeness Body Toggle.
- **Testability Notes:** Fully testable. The toggle arrow direction change and body visibility are visually verifiable. Requires an expected list to be imported first (can build on `decks_import_expected_and_completeness` setup).

#### 2f. `deck_detail_completeness_hidden_without_expected.yaml`

- **Description:** Navigate to a deck that is not a precon and has no expected list imported. Verify the completeness section is not visible on the page (hidden via `display: none`).
- **Priority:** Medium
- **UX Flows/States Covered:** State 7 (completeness section hidden).
- **Testability Notes:** Partially testable. Verifying that an element is hidden (not rendered) is tricky with screenshot-based testing -- the absence of the section below the card table is the indicator. Could be validated by checking that no "Expected Cards" heading appears anywhere on the page.

#### 2g. `deck_detail_completeness_precon_no_expected.yaml`

- **Description:** Navigate to a precon deck that has no expected list imported. Verify the completeness section is visible with the "(no expected list set)" message and guidance text.
- **Priority:** Medium
- **UX Flows/States Covered:** State 8 (completeness -- no expected list for precon).
- **Testability Notes:** Requires a precon deck without an expected list. Can reuse the precon creation flow from `decks_precon_origin_metadata`. The guidance text "Use 'Import Expected List' to define the expected cards for this deck." should be visible.

#### 2h. `deck_detail_expected_import_errors.yaml`

- **Description:** Open the Expected Import modal, attempt to import a malformed decklist (e.g., missing set code, invalid format), and verify that error text appears in red below the textarea. Verify the modal remains open and the user can correct the input.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 6 (import expected -- error path), State 15 (expected import modal), State 16 (expected import modal with errors).
- **Testability Notes:** Testability depends on the API's error response for malformed input. The red error text in `#expected-errors` is visually verifiable. The "empty textarea" alert path (State 15 + clicking Import with nothing) is a browser `alert()` which is harder to verify visually. **Limited testability for the `alert()` path.**

#### 2i. `deck_detail_add_cards_search_states.yaml`

- **Description:** Open the "Add Cards" modal, verify the initial "Type to search your collection..." message. Type one character, verify the "Type at least 2 characters..." message. Type a query that matches nothing, verify "No matching cards found". Type a query that matches cards, verify results appear.
- **Priority:** Medium
- **UX Flows/States Covered:** State 12 (add cards modal initial), State 13 (searching), State 14 (no results).
- **Testability Notes:** Fully testable through sequential typing and screenshot verification. Requires knowing a term that returns no results and one that does. The minimum character threshold (2 chars) behavior is the key edge case.

#### 2j. `deck_detail_edit_precon_fields.yaml`

- **Description:** Open a precon deck's Edit modal, verify precon-specific fields (origin set, theme, variation) are visible and pre-populated. Uncheck the precon checkbox, verify those fields hide. Re-check it, verify they reappear.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 4 (edit deck -- precon fields toggling), State 11 (edit modal).
- **Testability Notes:** Fully testable. Requires a precon deck. The toggle visibility of precon fields is a dynamic behavior that can be verified through sequential screenshots.

#### 2k. `deck_detail_modal_cancel_and_backdrop.yaml`

- **Description:** Open the Edit modal and close it via Cancel. Open the Add Cards modal and close it by clicking the backdrop. Open the Expected Import modal and close it via Cancel. Verify no data changes occur after each dismissal.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 10 (close any modal).
- **Testability Notes:** Partially testable. Clicking Cancel buttons is straightforward. Clicking the backdrop (outside the modal content) requires precise coordinate targeting which may be fragile. **Limited testability for backdrop-click dismissal.**

### Low Priority

These cover edge cases, error states, and behaviors that are implicitly tested by other intents.

#### 2l. `deck_detail_error_deck_not_found.yaml`

- **Description:** Navigate to `/decks/999999` (a non-existent deck ID). Verify the page shows an error state with "Deck not found" instead of the normal deck layout.
- **Priority:** Low
- **UX Flows/States Covered:** State 3 (error -- deck not found).
- **Testability Notes:** Fully testable. Navigate to a known-bad ID and verify the error message appears.

#### 2m. `deck_detail_remove_no_selection_alert.yaml`

- **Description:** Click "Remove Selected" without selecting any cards. Verify that an alert appears saying "No cards selected".
- **Priority:** Low
- **UX Flows/States Covered:** Flow 3 (remove cards -- no selection edge case).
- **Testability Notes:** **Limited testability.** Browser `alert()` dialogs are not visible in screenshots. Would need Playwright dialog handling in the implementation layer to verify. The main remove flow (2b) is more important.

#### 2n. `deck_detail_mana_cost_rendering.yaml`

- **Description:** View a deck with cards that have mana costs. Verify that mana cost symbols render as icons (not raw text like `{U}{B}`).
- **Priority:** Low
- **UX Flows/States Covered:** Dynamic Behavior: Mana Cost Rendering.
- **Testability Notes:** Partially testable. Mana icons depend on the mana-font CDN being reachable from the test container. If the CDN is unavailable, raw class names would appear instead. The visual difference between rendered icons and raw text is detectable in screenshots. Implicitly covered by `deck_detail_direct_navigation` if that test verifies the card table visually.

#### 2o. `deck_detail_page_title.yaml`

- **Description:** Navigate to a deck detail page and verify the browser page title is set to "{deck name} -- DeckDumpster".
- **Priority:** Low
- **UX Flows/States Covered:** Flow 1 (page load -- title setting).
- **Testability Notes:** **Limited testability.** Browser page title is not visible in page screenshots. Would require Playwright to read `document.title`. Implicitly covered by `deck_detail_direct_navigation` description which mentions the page title, but verifying it in a screenshot is not possible.

#### 2p. `deck_detail_select_all_checkbox.yaml`

- **Description:** Use the "Select All" checkbox to select all cards in the current zone, verify all row checkboxes are checked. Uncheck "Select All", verify all are unchecked. Switch zones, verify "Select All" resets.
- **Priority:** Low
- **UX Flows/States Covered:** Flow 3 (select cards -- select all behavior), Flow 2 (zone switch clears selections).
- **Testability Notes:** Fully testable but granular. Checkbox states are visible in screenshots. The cross-zone selection reset is an important behavioral detail. Partially overlaps with 2b (select and remove).

---

## 3. Coverage Matrix

| UX Section | Existing Intent(s) | Proposed Intent(s) | Coverage Status |
|---|---|---|---|
| **Flow 1:** Page load / view detail | `deck_detail_direct_navigation`, `deck_create_redirects_to_detail` | -- | Covered |
| **Flow 2:** Switch between zones | -- | `deck_detail_zone_tab_switching` (2a) | Gap -- High priority |
| **Flow 3:** Select and remove cards | -- | `deck_detail_select_and_remove_cards` (2b), `deck_detail_remove_no_selection_alert` (2m), `deck_detail_select_all_checkbox` (2p) | Gap -- High priority |
| **Flow 4:** Edit deck properties | `decks_precon_origin_metadata` (partial -- precon creation only) | `deck_detail_edit_properties` (2c), `deck_detail_edit_precon_fields` (2j) | Gap -- High priority |
| **Flow 5:** Add cards from collection | `decks_create_and_add_cards` (partial -- legacy view) | `deck_detail_add_cards_from_collection` (2d), `deck_detail_add_cards_search_states` (2i) | Gap -- High priority |
| **Flow 6:** Import expected card list | `decks_import_expected_and_completeness` | `deck_detail_expected_import_errors` (2h) | Mostly covered (error path is a gap) |
| **Flow 7:** View completeness tracking | `decks_import_expected_and_completeness` | `deck_detail_completeness_toggle` (2e), `deck_detail_completeness_hidden_without_expected` (2f), `deck_detail_completeness_precon_no_expected` (2g) | Partially covered (toggle and hidden states are gaps) |
| **Flow 8:** Reassemble missing cards | `decks_reassemble_unassigned_cards` | -- | Covered |
| **Flow 9:** Delete deck | `deck_detail_delete_redirects_to_list`, `decks_delete_keeps_cards` | -- | Covered |
| **Flow 10:** Close any modal | -- | `deck_detail_modal_cancel_and_backdrop` (2k) | Gap -- Medium priority |
| **State 1:** Loading | -- | -- | Not testable (transient, sub-second) |
| **State 2:** Error -- invalid URL | -- | -- | Not testable (requires malformed URL navigation, low value) |
| **State 3:** Error -- deck not found | -- | `deck_detail_error_deck_not_found` (2l) | Gap -- Low priority |
| **State 4:** Loaded with cards | `deck_detail_direct_navigation` | -- | Covered |
| **State 5:** Loaded with empty zone | -- | `deck_detail_zone_tab_switching` (2a) | Gap -- covered by proposed 2a |
| **State 6:** No cards at all | `deck_create_redirects_to_detail` (implicit) | -- | Partially covered |
| **State 7:** Completeness hidden | -- | `deck_detail_completeness_hidden_without_expected` (2f) | Gap -- Medium priority |
| **State 8:** Completeness -- precon no expected | -- | `deck_detail_completeness_precon_no_expected` (2g) | Gap -- Medium priority |
| **State 9:** Completeness -- full tracking | `decks_import_expected_and_completeness`, `decks_reassemble_unassigned_cards` | -- | Covered |
| **State 10:** Completeness -- collapsed | -- | `deck_detail_completeness_toggle` (2e) | Gap -- Medium priority |
| **State 11:** Edit modal open | `decks_precon_origin_metadata` (partial) | `deck_detail_edit_properties` (2c), `deck_detail_edit_precon_fields` (2j) | Gap -- High priority |
| **State 12:** Add cards modal -- initial | -- | `deck_detail_add_cards_search_states` (2i) | Gap -- Medium priority |
| **State 13:** Add cards modal -- searching | -- | `deck_detail_add_cards_from_collection` (2d), `deck_detail_add_cards_search_states` (2i) | Gap -- High priority |
| **State 14:** Add cards modal -- no results | -- | `deck_detail_add_cards_search_states` (2i) | Gap -- Medium priority |
| **State 15:** Expected import modal | `decks_import_expected_and_completeness` | -- | Covered |
| **State 16:** Expected import modal -- with errors | -- | `deck_detail_expected_import_errors` (2h) | Gap -- Medium priority |
| **State 17:** Confirm delete dialog | `deck_detail_delete_redirects_to_list` | -- | Covered |
| **Navigation:** Site header links | `deck_detail_direct_navigation` (implicit) | -- | Covered (header visible in screenshots) |
| **Navigation:** Card name links | `deck_detail_card_links_to_card_page` | -- | Covered |
| **Dynamic:** Mana cost rendering | `deck_detail_direct_navigation` (implicit) | `deck_detail_mana_cost_rendering` (2n) | Partially covered |
| **Dynamic:** Zone tab counts | `deck_detail_direct_navigation` (implicit) | `deck_detail_zone_tab_switching` (2a) | Partially covered |
| **Dynamic:** Page title | -- | `deck_detail_page_title` (2o) | Not screenshot-testable |
| **Dynamic:** Picker search (no debounce) | -- | `deck_detail_add_cards_search_states` (2i) | Gap -- Medium priority |
| **Dynamic:** Modal backdrop click | -- | `deck_detail_modal_cancel_and_backdrop` (2k) | Gap -- Medium priority |
| **Dynamic:** Reassemble button (conditional) | `decks_reassemble_unassigned_cards` | -- | Covered |

---

## 4. Intents with Limited Testability

| Proposed Intent | Limitation |
|---|---|
| `deck_detail_remove_no_selection_alert` (2m) | Browser `alert()` is not captured in screenshots. Requires Playwright dialog handler. |
| `deck_detail_page_title` (2o) | Page title is in the browser chrome, not the page content. Not visible in screenshots. |
| `deck_detail_modal_cancel_and_backdrop` (2k) | Backdrop click requires precise coordinate targeting outside modal content; may be fragile across viewport sizes. Cancel button path is fine. |
| `deck_detail_expected_import_errors` (2h) | The "empty textarea" sub-path triggers `alert()` (same limitation as 2m). The API error path with red text is fully testable. |
| `deck_detail_mana_cost_rendering` (2n) | Depends on CDN availability in the test container. Graceful degradation shows raw class names. |
| `deck_detail_completeness_hidden_without_expected` (2f) | Proving absence of a UI element is inherently weaker than proving presence. Relies on the section not appearing in the screenshot. |
| **State 1 (Loading)** -- no proposed intent | Transient state lasting sub-second; cannot be reliably captured. |
| **State 2 (Invalid URL)** -- no proposed intent | Requires navigating to a malformed URL. Low value; the JS error handling is trivial. |

---

## 5. Implementation Priority Summary

**Implement first (High -- 4 intents):**
1. `deck_detail_zone_tab_switching` -- core navigation within the page, no existing coverage
2. `deck_detail_select_and_remove_cards` -- core CRUD operation, no existing coverage
3. `deck_detail_edit_properties` -- core CRUD operation, existing coverage only for precon creation
4. `deck_detail_add_cards_from_collection` -- core CRUD operation, existing coverage is against legacy view

**Implement next (Medium -- 7 intents):**
5. `deck_detail_completeness_toggle` -- interactive behavior, easy to test
6. `deck_detail_completeness_hidden_without_expected` -- visual state verification
7. `deck_detail_completeness_precon_no_expected` -- visual state verification
8. `deck_detail_expected_import_errors` -- error path coverage
9. `deck_detail_add_cards_search_states` -- modal state progression
10. `deck_detail_edit_precon_fields` -- edit modal sub-behavior
11. `deck_detail_modal_cancel_and_backdrop` -- modal dismissal paths

**Implement last (Low -- 5 intents):**
12. `deck_detail_error_deck_not_found` -- error state
13. `deck_detail_remove_no_selection_alert` -- alert dialog (limited testability)
14. `deck_detail_mana_cost_rendering` -- visual detail (implicitly covered)
15. `deck_detail_page_title` -- not screenshot-testable
16. `deck_detail_select_all_checkbox` -- granular checkbox behavior (overlaps with 2b)
