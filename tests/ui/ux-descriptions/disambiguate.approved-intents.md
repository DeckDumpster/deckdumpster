# Disambiguate -- Approved Intents

Reviewed: 2026-03-09
Existing intents: 1 (`disambiguate_empty_state`)
Proposed new: 17
Result: 1 approved for implementation, 1 deferred, 15 cut

Fixture reality: `/api/ingest2/pending-disambiguation` returns `[]`. The test
fixture has NO cards in `READY_FOR_DISAMBIGUATION` state. This means every
proposed intent that requires a visible card block -- selecting candidates,
confirming cards, searching, expanding narrowed lists, the photo modal, finish
dropdown, metadata display, grid layout -- is completely untestable without
seeding the database with synthetic ingest pipeline records. This is not a
simple fixture gap: it requires `ingest_images` rows with valid `claude_result`
JSON, `scryfall_matches` JSON, `crops` JSON, `disambiguated` JSON arrays, and
accessible uploaded image files at the expected filesystem path.

Until the fixture is extended with disambiguation seed data, only the empty
state and static page structure are testable.

---

## Implement Now

- `disambiguate_navigation_links` -- Load `/disambiguate` and verify the header contains the "Disambiguate" title linking to Home, plus navigation links for Home (/), Upload (/upload), and Recent (/recent). Verify the empty state shows "No cards to disambiguate" with a link to the Upload page. This merges the structural parts of `disambiguate_page_structure` and `disambiguate_navigation_links` into one intent, testing everything visible in the empty-data state. The existing `disambiguate_empty_state` already covers the core empty message, but this broader intent also validates the nav bar structure and link targets, providing slightly more regression coverage for zero additional fixture cost.

## Deferred

- `disambiguate_full_flow` -- A combined intent covering candidate selection, finish dropdown, confirmation, and the "All done!" state. This would merge `disambiguate_select_candidate`, `disambiguate_confirm_card`, `disambiguate_confirm_all_done`, and `disambiguate_finish_dropdown` into a single end-to-end scenario. Defer until the test fixture includes at least one `READY_FOR_DISAMBIGUATION` record with valid metadata and candidate data. When that fixture work is done, implement this as a single high-value intent rather than four separate ones.

## Cut

- `disambiguate_page_structure` -- The structural parts are merged into `disambiguate_navigation_links`. The card-block verification requires pending data.
- `disambiguate_select_candidate` -- Requires pending disambiguation data. Merged into deferred `disambiguate_full_flow`.
- `disambiguate_confirm_card` -- Requires pending disambiguation data. Merged into deferred `disambiguate_full_flow`.
- `disambiguate_confirm_all_done` -- Requires pending disambiguation data. Merged into deferred `disambiguate_full_flow`.
- `disambiguate_manual_search` -- Requires pending disambiguation data. Low priority even with data (secondary flow).
- `disambiguate_show_all_candidates` -- Requires pending data AND a specific narrowing outcome. Double dependency makes it fragile.
- `disambiguate_photo_modal` -- Requires pending data with accessible uploaded images. Cannot test.
- `disambiguate_finish_dropdown` -- Requires pending data with foil-only candidates. Merged into deferred `disambiguate_full_flow`.
- `disambiguate_confirm_button_disabled_initial` -- Subsumed by `disambiguate_full_flow` (the disabled state is the starting point of any confirmation flow).
- `disambiguate_card_metadata_display` -- Requires pending data with complete OCR metadata. Cannot test.
- `disambiguate_crop_thumbnail` -- Requires pending data with crop coordinates and image files. Cannot test.
- `disambiguate_candidate_grid_layout` -- Requires pending data. Visual grid layout is low-value.
- `disambiguate_no_candidates_found` -- Requires pending data and a failing search query. Edge case not worth a dedicated intent even if data existed.
- `disambiguate_search_enter_key` -- Minor input method variation (Enter vs click). Not worth a separate intent.
- `disambiguate_status_bar_counter` -- Requires performing confirmations to test. Subsumed by deferred `disambiguate_full_flow`.
- `disambiguate_settings_image_display` -- Requires both pending data and a specific settings value. Double dependency, low value.
