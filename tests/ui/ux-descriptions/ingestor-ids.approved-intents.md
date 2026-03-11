# Manual ID Entry Page -- Approved Intents

Source: `tests/ui/ux-descriptions/ingestor-ids.test-plan.md`

## Existing Coverage

- **`manual_id_add_and_resolve`** -- Enter cards by set code + collector number, add to staging list, click Resolve, verify resolved cards show thumbnails and names.
- **`manual_id_rarity_mismatch`** -- Add card with wrong rarity, resolve, verify yellow warning "Expected R, got U".

## Core Advantage

This page is highly testable. All resolution happens against the local Scryfall database -- no external API calls. The fixture has populated card data. Decks and binders exist for assignment testing.

---

## Implement Now

### manual_id_page_initial_state
- **Description**: Verify the page loads with correct initial state: empty entry table with headers only (Rarity, CN, Set, Foil), card count "Cards: 0", Resolve button disabled, results panel showing info message "Add cards using rarity, collector number, and set code, then click Resolve." Home link present in header.
- **Testability**: Full -- no API calls needed.
- **Why now**: Validates the page contract. Pure DOM assertions.

### manual_id_keyboard_rapid_entry
- **Description**: Type collector number in CN input, press Enter to move focus to set input, type set code, press Enter to add entry. Verify CN input clears and re-focuses. Verify rarity and foil persist between entries (only CN is cleared). Add 3+ entries in quick succession.
- **Testability**: Full -- keyboard events and focus assertions. No API calls.
- **Why now**: The rapid-entry keyboard flow is the primary UX optimization of this page. Must verify it works.

### manual_id_remove_entry
- **Description**: Add several entries, click remove button on one, verify it is removed and count updates. Remove all entries, verify Resolve button becomes disabled.
- **Testability**: Full -- pure client-side DOM operations.
- **Why now**: Entry management is a core interaction. Simple, no API dependency for this phase.

### manual_id_failed_resolution
- **Description**: Add entries with invalid set codes or collector numbers (e.g., set "ZZZ", CN "9999"). Click Resolve. Verify "Failed (N)" section appears with error messages and "Edit & Retry" buttons. Click "Edit & Retry" on a failed entry, verify it moves back to the input list.
- **Testability**: Full -- use deliberately invalid data to trigger failures.
- **Why now**: Error handling and recovery flow. Critical user experience path.

### manual_id_resolve_and_commit
- **Description**: Add valid entries (use known cards from fixture, e.g., set "FDN", CN "150" or similar), set condition, fill batch name, click Resolve. Verify resolved table with card details. Select a deck from assign target dropdown, click "Add to Collection". Verify success message and state reset.
- **Testability**: Full -- requires valid set/CN combos in the fixture DB. The resolve and commit endpoints use local DB only.
- **Why now**: End-to-end happy path. The most important flow on the page.
- **Note**: Absorbs the proposed `manual_id_assign_to_binder` -- the assign target dropdown check (optgroups for Decks and Binders) is verified as part of this flow.

### manual_id_cancel_after_resolve
- **Description**: After resolving entries, click Cancel. Verify results panel shows "Cancelled. Add more cards to start over." Verify entry list remains intact.
- **Testability**: Full -- requires a successful resolve first.
- **Why now**: Cancel flow is a standard interaction. Simple assertion after resolve.

### manual_id_foil_toggle_in_results
- **Description**: After resolving cards, click the foil toggle on a non-foil card to see it change to gold "Foil" text. Click again to toggle back to gray "--". Verify the state change is visual and persistent.
- **Testability**: Full -- click events on `.foil-toggle` spans.
- **Why now**: Foil toggle is a per-card interaction unique to the results view. Not covered by existing intents.

---

## Deferred

### manual_id_remove_resolved_card
- **Reason**: Similar to `manual_id_remove_entry` but in the resolved table. Lower priority because the entry-side removal is more common and the resolved-side removal is a secondary action. Can be merged into `manual_id_foil_toggle_in_results` later as an extended interaction.

### manual_id_assign_to_binder
- **Reason**: Merged into `manual_id_resolve_and_commit`. The assign target dropdown (with both Decks and Binders optgroups) is verified there. Testing binder-specific assignment separately is redundant -- the dropdown mechanics are identical.

### manual_id_input_validation
- **Reason**: Low value. Testing that an empty CN or set code does nothing is a negative-case assertion. The behavior is "nothing happens" which is hard to assert meaningfully in a screenshot-based test.

### manual_id_commit_error
- **Reason**: Difficult to trigger reliably. Requires server-side manipulation or malformed data that passes resolve but fails commit.

### manual_id_resolve_api_error
- **Reason**: Difficult to trigger reliably without network interception.

### manual_id_mobile_layout
- **Reason**: Viewport manipulation for visual validation. Low priority. The desktop layout is the primary target.
