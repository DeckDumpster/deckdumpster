# Recent Page -- Approved Intents

Source: `tests/ui/ux-descriptions/recent.test-plan.md`

## Existing Coverage

- **`recent_page_overview`** -- Grid view with status-colored borders (green/red), card info.
- **`recent_view_toggle`** -- Toggle grid vs table view.
- **`recents/single_card_ingest`** -- Accordion "Add to Collection" for a single card.
- **`recents/brimstone_mage_ingest`** -- Demo ingest processing verification.

## Test Fixture State

The `--test` fixture has 4 ingest images: 2 DONE (Aetherflame Wall, Canyon Wildcat) and 2 ERROR. No processing or needs_disambiguation images exist. Decks (Bolt Tribal, Eldrazi Ramp) and binders (Trade Binder, Foil Collection) are available. No agent_trace data. Scryfall matches exist for the DONE images (1 candidate each).

---

## Implement Now

### recent_empty_state
- **Description**: Navigate to `/recent` with no ingest images in the pipeline. Verify "No recent images" heading, "Upload some photos" link pointing to `/upload`, Batch Ingest button hidden, summary text empty.
- **Testability**: Full -- requires clearing ingest data or testing on a fresh instance, but could also assert the empty state elements exist in the DOM and are shown/hidden correctly by checking CSS display.
- **Why now**: Validates a fundamental page state. No API dependencies. Simple DOM assertion.
- **Note**: May need to delete all 4 fixture images first (destructive) or verify the empty-state HTML elements exist but are display:none when images are present. Prefer the latter: just check that `#empty` div exists with the correct content, verify it becomes visible if no images load.

### recent_navigation_header
- **Description**: Verify header links: "Home" (/), "Upload" (/upload), "Disambiguate" (/disambiguate). Title "Recent Images" links to `/`. Clicking each navigates correctly.
- **Testability**: Full -- static HTML, no data dependencies.
- **Why now**: Navigation is a fundamental contract. Pure DOM check.

### recent_column_adjust
- **Description**: Click minus/plus buttons to change grid column count. Verify `#col-count` updates, minus disabled at 1, plus disabled at 12.
- **Testability**: Full -- column controls work regardless of data.
- **Why now**: Pure CSS/JS interaction. No API dependencies.

### recent_accordion_open_close
- **Description**: Click a DONE image card, verify white border + triangle indicator, accordion panel opens below the row. Verify sidebar shows card name and action buttons (Reprocess, Delete, Trace toggle). Click same card again to close.
- **Testability**: Testable -- fixture has 2 DONE images with scryfall_matches data.
- **Why now**: Core interaction pattern. Verifies the most important interactive element on the page.

### recent_status_summary_counts
- **Description**: Verify summary line above grid shows counts: "4 image(s): 2 done, 2 error" (matching fixture data).
- **Testability**: Testable -- fixture has known counts.
- **Why now**: Validates a visible and important data display. Simple text assertion.

### recent_card_status_borders
- **Description**: DONE cards have green border (`.done` class), ERROR cards have red border (`.error` class). Error cards show a red "x" icon.
- **Testability**: Testable -- fixture has both DONE and ERROR cards.
- **Why now**: Visual status indication is a core page contract. Merge with `recent_page_overview`? No -- overview is broader; this is a focused assertion on CSS classes.
- **Note**: Merges the proposed `recent_error_card_tooltip` (hover tooltip on error cards) into this intent. The tooltip assertion can be included as a secondary check.

### recent_batch_ingest
- **Description**: With DONE cards present, verify the green "Batch Ingest" button is visible. Click it. Verify done cards are removed, success message with Collection link appears.
- **Testability**: Testable -- fixture has 2 DONE cards. Destructive (removes cards from grid).
- **Why now**: Primary workflow completion action. Must run AFTER accordion/status tests due to destructive nature.

### recent_assign_target_dropdown
- **Description**: Verify `#assign-target` dropdown has "No assignment" default, "Decks" optgroup (Bolt Tribal, Eldrazi Ramp), "Binders" optgroup (Trade Binder, Foil Collection).
- **Testability**: Full -- dropdown is populated on page load from API.
- **Why now**: Verifies the dropdown is populated correctly. Simple select element assertion.

---

## Deferred

### recent_single_card_ingest
- **Reason**: Already covered by `recents/single_card_ingest` existing intent.

### recent_delete_image
- **Reason**: Uses `window.confirm()` dialog. Playwright can handle this via dialog event handlers, but it adds complexity. The destructive action also conflicts with other tests sharing the same fixture data. Defer until dialog handling is standardized.

### recent_reprocess_image
- **Reason**: Uses `window.confirm()` dialog. Also, reprocessing requires ANTHROPIC_API_KEY for the agent pipeline, so the card would remain in an error state without it. Untestable in the standard test harness.

### recent_accordion_candidate_select
- **Reason**: Fixture DONE images have only 1 candidate each (scryfall_matches has a single match). Cannot test "click a different candidate" when there is only one. Needs richer fixture data.

### recent_search_alternative_card
- **Reason**: Requires `POST /api/ingest2/search-card` which queries the local Scryfall cache. Testable in theory, but depends on specific card data being in the cache. Medium priority deferred until fixture data is validated.

### recent_finish_badge_quick_action
- **Reason**: Requires DONE cards with multiple finish options in `finish_options` array. Fixture data has single-finish cards. Needs richer fixture.

### recent_agent_trace_toggle
- **Reason**: Fixture has `agent_trace: False` for the DONE images. The trace panel would have no content to display. Needs fixture data with populated trace.

### recent_done_card_overlays
- **Reason**: Partially covered by `recent_page_overview` and `recent_card_status_borders`. The overlay details (Keyrune icons, foil shimmer) depend on external CDN resources (Keyrune font, Scryfall images) that may not load in test environments.

### recent_table_mode_layout
- **Reason**: Partially covered by `recent_view_toggle`. The detailed table mode assertions (Scryfall thumbnails, info-rows) depend on lazy-loaded external images.

### recent_usage_stats_display
- **Reason**: Requires images processed through Claude agent pipeline to generate usage data. Fixture has no usage data (no API processing occurred).

### recent_processing_poll
- **Reason**: Timing-dependent. Requires an image actively being processed. No ANTHROPIC_API_KEY in test environment.

### recent_discovery_poll
- **Reason**: Timing-dependent (20-second interval). Requires uploading from a separate session. Impractical for automated tests.

### recent_error_card_tooltip
- **Reason**: Merged into `recent_card_status_borders`.

### recent_crop_zoom
- **Reason**: Visual-only CSS assertion. Low value relative to implementation effort.

### recent_accordion_no_cards_detected
- **Reason**: Fixture ERROR images have no cards detected but also have error status -- the accordion behavior for ERROR cards may differ from a "no cards detected" DONE card. Difficult to seed this specific state.

### recent_accordion_already_ingested
- **Reason**: Requires ingesting a card first, then re-opening its accordion. The image is removed from the grid after ingest, making this state hard to observe.

### recent_view_mode_persistence
- **Reason**: Low value. localStorage persistence is a trivial JS feature.

### recent_accordion_show_all_candidates
- **Reason**: Requires fixture data where narrowing produces a subset. Single-candidate fixture data makes this untestable.

### recent_batch_ingest_with_assignment
- **Reason**: The assignment dropdown is tested separately. The interaction between assignment and batch ingest is an API-level concern, not a UI-level one.

### recent_keyrune_fallback_map
- **Reason**: Niche. Requires cards from specific sets with mismatched codes. Extremely low ROI.

### recent_mobile_layout (not proposed but implied)
- **Reason**: Not proposed in test plan. Would require viewport manipulation for visual validation.
