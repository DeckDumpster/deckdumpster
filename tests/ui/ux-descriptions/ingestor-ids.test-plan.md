# Test Plan: Manual ID Entry Page (`/ingestor-ids`)

## 1. Existing Intents

| Intent File | Summary |
|-------------|---------|
| `manual_id_add_and_resolve.yaml` | Enter cards by set code and collector number on the Manual ID Entry page, add entries to the staging list, click Resolve, and verify resolved cards show thumbnails and names. |
| `manual_id_rarity_mismatch.yaml` | Add a card with a rarity that does not match the actual card rarity, resolve, and verify a yellow warning appears showing expected vs actual rarity. |

---

## 2. Proposed New Intents

### High Priority

#### `manual_id_page_initial_state.yaml`
- **Description:** Verify the Manual ID Entry page loads with correct initial state: empty entry table with headers only, card count showing "Cards: 0", Resolve button disabled, results panel showing the info message "Add cards using rarity, collector number, and set code, then click Resolve." Navigation link to Home is present.
- **Priority:** High
- **UX Flows/States Covered:** On Page Load, Input Panel State (Empty entry list), Results Panel State (Initial), Section 2 (Navigation)
- **Testability Notes:** Fully testable. No API calls needed. Verify DOM elements and their states.

#### `manual_id_keyboard_rapid_entry.yaml`
- **Description:** Verify the keyboard-driven rapid entry flow: type a collector number and press Enter to move focus to set input, type a set code and press Enter to add the entry. Confirm the CN input clears and re-focuses. Verify rarity and foil persist across entries while CN is cleared. Add multiple entries in quick succession this way.
- **Priority:** High
- **UX Flows/States Covered:** Flow 2 (Keyboard-Driven Rapid Entry), Quick Add Input Handling
- **Testability Notes:** Fully testable. Uses keyboard events and focus assertions. No API calls needed for the entry phase.

#### `manual_id_resolve_and_commit.yaml`
- **Description:** Add entries, fill in batch metadata (batch name, product type, batch set code), set condition, click Resolve, verify the resolved table appears with card details. Then select a deck from the assign target dropdown and click "Add to Collection". Verify success message and state reset.
- **Priority:** High
- **UX Flows/States Covered:** Flow 4 (Resolve Entries), Flow 7 (Commit Cards to Collection), Results Panel States (Resolving, Resolved all success, Committing, Commit success)
- **Testability Notes:** Testable. Requires valid set codes and collector numbers present in the test fixture database. The resolve endpoint uses the local DB, no external API calls.

#### `manual_id_failed_resolution.yaml`
- **Description:** Add entries with invalid set codes or collector numbers that will not resolve. Click Resolve and verify the "Failed (N)" section appears with error messages and "Edit & Retry" buttons. Click "Edit & Retry" on a failed entry and verify it moves back to the input list for correction.
- **Priority:** High
- **UX Flows/States Covered:** Flow 6 (Handle Failed Resolutions), Results Panel States (Resolved mixed, Resolved all failed)
- **Testability Notes:** Fully testable. Use deliberately invalid set/CN combinations to trigger failures.

### Medium Priority

#### `manual_id_remove_entry.yaml`
- **Description:** Add several entries to the staging list, then click the remove button on one entry. Verify the entry is removed, the table re-renders, and the card count updates. Remove all entries and verify the Resolve button becomes disabled.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 3 (Remove an Entry Before Resolving), Resolve Button State
- **Testability Notes:** Fully testable. Pure client-side DOM operations.

#### `manual_id_cancel_after_resolve.yaml`
- **Description:** After resolving entries, click the Cancel button and verify the results panel shows "Cancelled. Add more cards to start over." Confirm that the entry list remains intact for re-use.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 8 (Cancel After Resolution), Results Panel State (Cancelled)
- **Testability Notes:** Fully testable. Requires a successful resolve first, then verifying cancel behavior.

#### `manual_id_foil_toggle_in_results.yaml`
- **Description:** After resolving cards, verify the foil toggle in the resolved table works: click to toggle a non-foil card to foil (shows gold "Foil" text), click again to toggle back (shows gray "--"). Verify the state change persists through commit.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 5 (Review and Adjust Resolved Cards), Foil toggle behavior in results
- **Testability Notes:** Fully testable. Click events on `.foil-toggle` spans and verify visual state changes.

#### `manual_id_remove_resolved_card.yaml`
- **Description:** After resolving multiple cards, remove one card from the resolved list via the remove button. Verify the card is removed and the summary count updates.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 5 (Review and Adjust Resolved Cards) -- remove from resolved list
- **Testability Notes:** Fully testable. Click `.remove-btn[data-resolved-idx]` and verify DOM changes.

#### `manual_id_assign_to_binder.yaml`
- **Description:** After resolving cards, select a binder (not a deck) from the assign target dropdown and commit. Verify the assignment uses the `binder:ID` format and the cards are added to the collection with binder assignment.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 7 with binder assignment, Assign Target Loading (optgroups for Decks and Binders)
- **Testability Notes:** Testable if binders exist in the test fixture. Verify the dropdown has separate optgroups for Decks and Binders.

### Low Priority

#### `manual_id_input_validation.yaml`
- **Description:** Attempt to add an entry with an empty collector number or empty set code and verify nothing is added (addEntry returns without action). Verify the entry list stays unchanged.
- **Priority:** Low
- **UX Flows/States Covered:** Quick Add Input Handling (validation: both CN and Set must be non-empty)
- **Testability Notes:** Fully testable. Try clicking Add with empty fields and verify no rows appear.

#### `manual_id_commit_error.yaml`
- **Description:** Trigger a commit failure (e.g., by sending malformed data) and verify a red error message appears and the commit button re-enables with original text.
- **Priority:** Low
- **UX Flows/States Covered:** Results Panel State (Commit error)
- **Testability Notes:** Difficult to trigger reliably. Would require intercepting the API request or manipulating state to cause a server error.

#### `manual_id_resolve_api_error.yaml`
- **Description:** Trigger a resolution API error and verify a red error message appears in the results panel.
- **Priority:** Low
- **UX Flows/States Covered:** Results Panel State (API error)
- **Testability Notes:** Difficult to trigger reliably without server-side manipulation or network interception.

#### `manual_id_mobile_layout.yaml`
- **Description:** Verify the mobile layout: single-column stacking with input panel above results panel, entry list max-height 150px, smaller thumbnails (24x33px), reduced font and padding.
- **Priority:** Low
- **UX Flows/States Covered:** Layout States (Mobile <= 768px)
- **Testability Notes:** Testable with viewport resizing in Playwright. Set viewport to 375x667 and verify layout changes. Requires screenshot comparison for visual validation.

---

## 3. Coverage Matrix

| UX Description Section | Existing Intents | Proposed Intents |
|------------------------|-----------------|-----------------|
| **Navigation (Section 2)** | -- | `manual_id_page_initial_state` |
| **Rarity dropdown (Section 3)** | `manual_id_add_and_resolve` (implicit) | `manual_id_keyboard_rapid_entry` |
| **CN input (Section 3)** | `manual_id_add_and_resolve` | `manual_id_keyboard_rapid_entry`, `manual_id_input_validation` |
| **Set input (Section 3)** | `manual_id_add_and_resolve` | `manual_id_keyboard_rapid_entry`, `manual_id_input_validation` |
| **Foil checkbox (Section 3)** | -- | `manual_id_keyboard_rapid_entry` (persistence) |
| **Add button (Section 3)** | `manual_id_add_and_resolve` | `manual_id_input_validation` |
| **Entry table (Section 3)** | `manual_id_add_and_resolve` | `manual_id_remove_entry` |
| **Remove buttons in entry table (Section 3)** | -- | `manual_id_remove_entry` |
| **Card count (Section 3)** | -- | `manual_id_page_initial_state`, `manual_id_remove_entry` |
| **Condition dropdown (Section 3)** | -- | `manual_id_resolve_and_commit` |
| **Batch name/product type/set code (Section 3)** | -- | `manual_id_resolve_and_commit` |
| **Resolve button (Section 3)** | `manual_id_add_and_resolve` | `manual_id_page_initial_state` (disabled state) |
| **Assign target dropdown (Section 3)** | -- | `manual_id_resolve_and_commit`, `manual_id_assign_to_binder` |
| **Commit button (Section 3)** | -- | `manual_id_resolve_and_commit` |
| **Cancel button (Section 3)** | -- | `manual_id_cancel_after_resolve` |
| **Foil toggles in results (Section 3)** | -- | `manual_id_foil_toggle_in_results` |
| **Remove resolved buttons (Section 3)** | -- | `manual_id_remove_resolved_card` |
| **Edit & Retry buttons (Section 3)** | -- | `manual_id_failed_resolution` |
| **Flow 1: Add Single Entry** | `manual_id_add_and_resolve` | `manual_id_page_initial_state` |
| **Flow 2: Keyboard Rapid Entry** | -- | `manual_id_keyboard_rapid_entry` |
| **Flow 3: Remove Entry** | -- | `manual_id_remove_entry` |
| **Flow 4: Resolve Entries** | `manual_id_add_and_resolve` | `manual_id_resolve_and_commit` |
| **Flow 5: Review Resolved** | `manual_id_rarity_mismatch` (warning) | `manual_id_foil_toggle_in_results`, `manual_id_remove_resolved_card` |
| **Flow 6: Handle Failed** | -- | `manual_id_failed_resolution` |
| **Flow 7: Commit to Collection** | -- | `manual_id_resolve_and_commit` |
| **Flow 8: Cancel After Resolution** | -- | `manual_id_cancel_after_resolve` |
| **State: Empty entry list** | -- | `manual_id_page_initial_state` |
| **State: Entries queued** | `manual_id_add_and_resolve` | `manual_id_keyboard_rapid_entry` |
| **State: Resolving** | -- | `manual_id_resolve_and_commit` |
| **State: Initial results panel** | -- | `manual_id_page_initial_state` |
| **State: Resolving spinner** | `manual_id_add_and_resolve` (implicit) | `manual_id_resolve_and_commit` |
| **State: Resolved (all success)** | `manual_id_add_and_resolve` | `manual_id_resolve_and_commit` |
| **State: Resolved (mixed)** | -- | `manual_id_failed_resolution` |
| **State: Resolved (all failed)** | -- | `manual_id_failed_resolution` |
| **State: API error** | -- | `manual_id_resolve_api_error` |
| **State: Committing** | -- | `manual_id_resolve_and_commit` |
| **State: Commit success** | -- | `manual_id_resolve_and_commit` |
| **State: Commit error** | -- | `manual_id_commit_error` |
| **State: Cancelled** | -- | `manual_id_cancel_after_resolve` |
| **State: Rarity mismatch warning** | `manual_id_rarity_mismatch` | -- |
| **Layout: Desktop** | `manual_id_add_and_resolve` (implicit) | -- |
| **Layout: Mobile** | -- | `manual_id_mobile_layout` |

### Testability Summary

The Manual ID Entry page is well-suited for automated testing because its core flow (add entries, resolve against local DB, commit) does not depend on external services like Claude Vision. All resolution happens against the local Scryfall database.

- **Fully testable:** `manual_id_page_initial_state`, `manual_id_keyboard_rapid_entry`, `manual_id_remove_entry`, `manual_id_resolve_and_commit`, `manual_id_failed_resolution`, `manual_id_cancel_after_resolve`, `manual_id_foil_toggle_in_results`, `manual_id_remove_resolved_card`, `manual_id_assign_to_binder`, `manual_id_input_validation`
- **Testable with viewport manipulation:** `manual_id_mobile_layout`
- **Difficult to trigger reliably:** `manual_id_commit_error`, `manual_id_resolve_api_error`

### Coverage Gaps

- **Batch metadata** (batch name, product type, batch set code) is only indirectly tested through the commit flow. No existing intent verifies these fields are sent correctly or appear in batch records.
- **Assign target dropdown optgroups** (Decks vs Binders separation) are not covered by existing intents.
- **Edit & Retry flow** for failed resolutions has no existing coverage.
- **Rarity mismatch** is covered by one existing intent but only for the warning display, not for how the user proceeds after seeing the warning.
