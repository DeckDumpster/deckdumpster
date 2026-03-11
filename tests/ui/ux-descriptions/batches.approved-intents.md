# Batches Page -- Approved Intents

Reviewed 18 proposed intents from `batches.test-plan.md` against:
- 3 existing batches intents (`batches_homepage_nav_link`, `batches_type_filter_bar`, `batches_detail_view_and_metadata`)
- 2 existing corners intents that exercise the same features (`corners_batch_browse`, `corners_batch_retroactive_deck_assign`)
- Live container state: 2 corner-type batches only (no OCR/CSV/manual/order), 1 assigned to deck, 1 unassigned, all cards have images, no metadata fields populated

---

## Implement Now

### 1. `batches_assign_unassigned_to_deck`

**Description:** When I view an unassigned batch ("New cards from LGS"), I see a deck dropdown populated with existing decks, a zone dropdown defaulting to Mainboard, and an Assign button. I select "Eldrazi Ramp", leave zone as Mainboard, and click Assign. A green success message appears showing the number of cards assigned, and the dropdowns are replaced by a green "Assigned to: Eldrazi Ramp (mainboard)" status.

**Why keep:** This is the primary write operation on the batches page. The existing `corners_batch_retroactive_deck_assign` tests this flow from the corners page, but the batches page has its own distinct UI (different dropdown IDs, different detail layout). This is the single highest-value new intent for the batches page.

**Fixture requirements:** Batch 2 is unassigned. Decks "Bolt Tribal" and "Eldrazi Ramp" exist. Straightforward.

### 2. `batches_already_assigned_view`

**Description:** When I click into batch "Wednesday evening scan" (already assigned to "Bolt Tribal"), I see a green "Assigned to: Bolt Tribal (sideboard)" status message instead of deck/zone dropdowns and an Assign button. No assignment controls are available.

**Why keep:** Tests a distinct visual state from the unassigned case. The existing `batches_detail_view_and_metadata` intent does not verify assignment status rendering. Batch 1 already has this state in the fixture -- no setup needed.

**Fixture requirements:** Batch 1 is already assigned. No action needed.

### 3. `batches_detail_back_preserves_filter`

**Description:** I click the "Corner" filter pill, see the filtered list, then click into a batch detail. When I click "Back", the list view reappears still showing the Corner filter as active and the same filtered results.

**Why keep:** Tests an interaction sequence that crosses view boundaries (filter -> detail -> back). The existing `batches_detail_view_and_metadata` tests the Back button but not filter state preservation. The existing `batches_type_filter_bar` tests filtering but never enters detail view. This fills a real gap.

**Fixture requirements:** Both batches are corner type, so the filtered and unfiltered views look the same. The test still verifies the pill stays active and the list re-renders without a full page reload.

### 4. `batches_filter_empty_result`

**Description:** When I click the "OCR" filter pill (which matches no batches in the fixture), the batch grid is replaced by the empty-state message "No batches yet. Import cards via CSV, corners, or orders to create batches." Switching back to "All" restores the full batch list.

**Why keep:** Tests a boundary condition (empty filtered results) that is distinct from the populated filter case in `batches_type_filter_bar`. The fixture naturally supports this -- no OCR batches exist. Simple, fast, and catches regressions where the empty state fails to render or the "All" reset breaks.

**Fixture requirements:** No OCR batches in fixture. Already true.

### 5. `batches_deck_label_in_list`

**Description:** In the batch list view, the batch "Wednesday evening scan" (assigned to "Bolt Tribal") shows a green "Deck: Bolt Tribal" label on its card. The batch "New cards from LGS" (unassigned) does not show a deck label.

**Why keep:** Tests list-level rendering of assignment status, which is visually distinct from the detail-level assigned state tested in `batches_already_assigned_view`. The existing `batches_homepage_nav_link` checks card counts and type badges but not deck labels. Both states are present in the fixture simultaneously.

**Fixture requirements:** One assigned, one unassigned batch. Already true.

---

## Deferred

### `batches_page_header_and_navigation`

**Reason: Redundant.** The existing `batches_homepage_nav_link` already navigates to `/batches` and verifies the page loads with batch names, card counts, and type badges. Verifying that header links to `/` and `/collection` work is generic navigation testing -- low signal for a page-specific test suite. If we want nav-link coverage, it belongs in a cross-cutting "site navigation" intent, not here.

### `batches_list_view_populated`

**Reason: Redundant.** The existing `batches_homepage_nav_link` already verifies that the batch list renders with names, card counts, and type badges. Adding another intent that checks the same grid rendering adds no new coverage.

### `batches_filter_each_type`

**Reason: Redundant + untestable with fixture.** The existing `batches_type_filter_bar` already tests pill activation and filtering (Corner, All). Testing all 6 pills individually is low value when the fixture only contains corner-type batches -- clicking OCR/CSV/Manual/Orders all produce the same empty result. The meaningful gap (empty filtered result) is covered by `batches_filter_empty_result` above.

### `batches_detail_card_grid_with_images`

**Reason: Redundant.** The existing `batches_detail_view_and_metadata` already enters the detail view and verifies cards are displayed with names and set information. Card images rendering with lazy loading is a visual detail best caught by screenshot diffing, not a separate scenario.

### `batches_detail_info_section`

**Reason: Untestable with fixture.** The fixture batches have no `product_type`, `set_code`, `notes`, or order metadata. The info section would show only the batch type and date, which `batches_detail_view_and_metadata` already covers. Creating a test for metadata display when no metadata exists in the fixture produces a test that verifies the absence of content -- not useful.

### `batches_detail_card_fallback_image`

**Reason: Untestable with fixture.** All cards in both batches have `image_uri` populated. Testing fallback images requires cards with null `image_uri`, which the demo fixture does not produce. Would need custom fixture manipulation.

### `batches_assign_to_sideboard_zone`

**Reason: Low marginal value.** The `batches_assign_unassigned_to_deck` intent already exercises the full assignment flow. Changing the zone dropdown from Mainboard to Sideboard tests one extra select interaction. The `batches_already_assigned_view` intent already verifies "(sideboard)" rendering via batch 1. The zone dropdown is a standard HTML `<select>` -- if Mainboard works, Sideboard works.

### `batches_assign_no_deck_selected`

**Reason: Negative test with low value.** Verifying that clicking Assign with no deck selected does nothing (no API call, no error) tests a single `if (!deckId) return;` guard. This is a code-level concern, not a user-facing scenario. If it regresses, the worst outcome is a harmless API error.

### `batches_type_color_coding`

**Reason: Visual detail, untestable with fixture.** Color verification (#e94560 for corner, #88c0d0 for OCR, etc.) requires inspecting computed CSS styles, which Claude Vision screenshot tests handle poorly. The fixture only has corner-type batches, so only one color would be tested anyway.

### `batches_empty_state`

**Reason: Requires special fixture.** The test needs a database with zero batches. The standard test fixture includes batches by default. This is effectively tested as a sub-step of `batches_filter_empty_result` (which triggers the same empty-state div by filtering to a type with no matches).

### `batches_assign_success_message_auto_dismiss`

**Reason: Timing-dependent, flaky.** Waiting 10 seconds for auto-dismiss in a test is slow and brittle. The success message appearing is already verified by `batches_assign_unassigned_to_deck`. Auto-dismiss is a `setTimeout` -- either it works or it doesn't, and a flaky test does not help.

### `batches_assign_error_message`

**Reason: Difficult to trigger.** Requires forcing an API error (e.g., assigning to a nonexistent deck ID, which means bypassing the dropdown). The test plan itself notes limited testability. Error message styling is the same pattern used across the entire app.

### `batches_metadata_display_variants`

**Reason: Untestable with fixture.** No order-type or CSV-import batches exist. No batches have `product_type`, `set_code`, `order_number`, or `seller_name` populated. Would need entirely different fixture data.

### `batches_mobile_responsive_layout`

**Reason: Cross-cutting concern.** Responsive layout is a CSS media query test. The test harness uses a fixed viewport. Testing mobile layout requires viewport resizing, which is an infrastructure concern, not a batches-page-specific scenario. If responsive testing is added, it should cover all pages, not just batches.

---

## Summary

| Category | Count | Intents |
|----------|-------|---------|
| Existing (keep) | 3 | `batches_homepage_nav_link`, `batches_type_filter_bar`, `batches_detail_view_and_metadata` |
| Implement now | 5 | `batches_assign_unassigned_to_deck`, `batches_already_assigned_view`, `batches_detail_back_preserves_filter`, `batches_filter_empty_result`, `batches_deck_label_in_list` |
| Deferred | 13 | Cut for redundancy, fixture limitations, or low marginal value |
| **Total active** | **8** | 3 existing + 5 new |

The 18 proposed intents are cut to 5. Combined with 3 existing intents, the batches page has 8 scenarios covering: page load and navigation, list rendering with deck labels, type filtering (populated and empty results), detail view entry and exit with filter preservation, assigned vs. unassigned batch states, and the full deck assignment flow.
