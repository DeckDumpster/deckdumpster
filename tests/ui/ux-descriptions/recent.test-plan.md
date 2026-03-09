# Recent/Process Page (`/recent`) -- Test Plan

Source: `tests/ui/ux-descriptions/recent.md`

## Existing Coverage

The following existing intents cover recent page scenarios:

- **`recent_page_overview`** -- Navigates to the Recent Images page and verifies that ingest pipeline images are displayed with status-colored borders (green for done, red for errors) and card information in the image grid.
- **`recent_view_toggle`** -- Toggles between grid view and table view using the view toggle button, verifying that table view shows additional details in list format and grid view shows image cards.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### High Priority

### recent_empty_state
- **Description**: When I navigate to the Recent Images page with no images in the ingest pipeline, I see a centered "No recent images" heading with an "Upload some photos" link (red text) that navigates to `/upload`. The Batch Ingest button is hidden and the summary text is empty.
- **References**: UX Description S7 Visual States > Empty State, S2 Navigation > "Upload some photos"
- **Testability**: full (requires an empty ingest pipeline, which is the default state without uploading images; can be achieved by ensuring no ingest_images records exist)
- **Priority**: high

### recent_navigation_header
- **Description**: When I visit the Recent Images page, I can see header navigation links for "Home" (/), "Upload" (/upload), and "Disambiguate" (/disambiguate). The page title "Recent Images" in the header links back to the homepage. Clicking each link navigates to the correct destination.
- **References**: UX Description S2 Navigation (header links)
- **Testability**: full (navigation links are present in the static HTML regardless of data state)
- **Priority**: high

### recent_status_summary_counts
- **Description**: When I navigate to the Recent Images page with images in various processing states, I see a summary line above the grid showing counts in the format "{N} image(s): {X} processing, {Y} done, {Z} need disambiguation, {W} error". The counts accurately reflect the status of all images in the pipeline.
- **References**: UX Description S4 User Flows > Flow 1 (step 4), S5 Dynamic Behavior > On Page Load
- **Testability**: limited (requires ingest_images records in multiple statuses seeded in the database; the --test fixture includes demo ingest data with done status but may not include all statuses)
- **Priority**: high

### recent_accordion_open_close
- **Description**: When I click an image card in the grid, the card gets a white border with a downward-pointing triangle indicator and an accordion panel slides open below the card's row spanning all columns. The panel shows a sidebar with the card name, action buttons (Reprocess, Trace toggle, Delete), and a main area with candidate card printings. Clicking the same card again closes the accordion.
- **References**: UX Description S4 User Flows > Flow 2, S3 Interactive Elements > Accordion Panel, S7 Visual States > Selected Card State, Accordion Open State
- **Testability**: limited (requires ingest_images records with done status and associated scryfall_matches data; demo ingest samples may provide this)
- **Priority**: high

### recent_batch_ingest
- **Description**: When at least one card has "done" status, the green "Batch Ingest" button appears in the controls bar. Clicking it sends all done images to the collection and on success: all done cards are removed from the grid, the accordion closes if open, and a success message "{N} photo(s) inserted: See them in Collection." appears with a link to `/collection`.
- **References**: UX Description S4 User Flows > Flow 6, S3 Interactive Elements > #batch-btn, #batch-msg, S7 Visual States > Batch Ingest Success State
- **Testability**: limited (requires ingest_images records in done status with confirmed scryfall matches; the batch ingest call modifies state so subsequent assertions must check for card removal and message display)
- **Priority**: high

### recent_delete_image
- **Description**: When I open the accordion for any card and click the red "Delete" button, a confirmation dialog appears asking "Delete this image and any collection entries from it?". If I confirm, the card is removed from the grid and the accordion closes.
- **References**: UX Description S4 User Flows > Flow 9, S3 Interactive Elements > Delete button
- **Testability**: limited (requires ingest_images records; must handle the window.confirm dialog via Playwright's dialog handler; destructive action that modifies state)
- **Priority**: high

### recent_card_status_borders
- **Description**: Cards in the grid display color-coded borders reflecting their processing status: grey border for processing cards, green border for done cards, red border for needs_disambiguation or error cards. Error cards additionally show a large red "x" icon centered over the image.
- **References**: UX Description S7 Visual States > Processing State, Done State, Needs Disambiguation State, Error State
- **Testability**: limited (requires ingest_images records in multiple statuses; the --test fixture may only have done and error states)
- **Priority**: high

### recent_single_card_ingest
- **Description**: When I open the accordion for a done card, I can see an "Add to Collection" button in the sidebar. Clicking it ingests that single card into the collection (with optional assign_target), removes the card from the grid, and closes the accordion.
- **References**: UX Description S4 User Flows > Flow 7, S3 Interactive Elements > "Add to Collection" button
- **Testability**: limited (requires ingest_images records in done status with confirmed scryfall match; destructive action that modifies state)
- **Priority**: high

### Medium Priority

### recent_accordion_candidate_select
- **Description**: When I open the accordion for a done or pending card, I can see candidate card printings as clickable tiles with Scryfall images, set icons (Keyrune), collector numbers, and finish overlays. Clicking a different candidate tile sends a confirm or correct API call, the accordion refreshes, and the grid card updates its overlays (set icon, finish badge, card title).
- **References**: UX Description S4 User Flows > Flow 3, S3 Interactive Elements > .acc-candidate
- **Testability**: limited (requires ingest_images records with multiple scryfall_matches candidates; the currently selected candidate must have a green border)
- **Priority**: medium

### recent_search_alternative_card
- **Description**: When I open the accordion for any card, I can modify the search input text (pre-filled with the detected card name), optionally enter a set code in the set code input, and press Enter. The candidate area is replaced with search results. I can then click a result to confirm or correct the identification.
- **References**: UX Description S4 User Flows > Flow 4, S3 Interactive Elements > #acc-search-input, #acc-set-input
- **Testability**: limited (requires ingest_images records; the search calls POST /api/ingest2/search-card which queries the local Scryfall cache)
- **Priority**: medium

### recent_column_adjust
- **Description**: I can click the minus and plus buttons in the column controls to decrease or increase the grid column count. The minus button is disabled at 1 column and the plus button is disabled at 12 columns. The column count display updates. If the accordion is open, it repositions to stay in the correct row.
- **References**: UX Description S4 User Flows > Flow 12, S3 Interactive Elements > #col-minus, #col-count, #col-plus
- **Testability**: full (column controls are functional regardless of image data; can verify CSS variable changes and button disabled states)
- **Priority**: medium

### recent_assign_target_dropdown
- **Description**: The controls bar contains an assignment dropdown (#assign-target) populated with decks (under "Decks" optgroup) and binders (under "Binders" optgroup) fetched from the API on page load. The default option is "No assignment". Selecting a target applies it to subsequent batch or single-card ingest operations.
- **References**: UX Description S3 Interactive Elements > #assign-target, S5 Dynamic Behavior > On Page Load > loadAssignTargets()
- **Testability**: limited (requires decks and/or binders in the database to populate the dropdown; the --test fixture should include demo decks and binders)
- **Priority**: medium

### recent_finish_badge_quick_action
- **Description**: A done card with multiple finish options (e.g., foil and nonfoil) shows clickable finish badges overlaid on the card image. Clicking a badge changes the finish via an API call, the clicked badge gets a green active border, and the foil shimmer overlay toggles accordingly.
- **References**: UX Description S4 User Flows > Flow 5, S3 Interactive Elements > .finish-badge
- **Testability**: limited (requires ingest_images records for a card that has multiple finish options in its finish_options array; badge click triggers a confirm/correct API call)
- **Priority**: medium

### recent_reprocess_image
- **Description**: When I open the accordion for any card and click the "Reprocess" button, a confirmation dialog appears. If confirmed, the image is reset and the page data reloads. The accordion closes and the card returns to a processing state.
- **References**: UX Description S4 User Flows > Flow 8, S3 Interactive Elements > Reprocess button
- **Testability**: limited (requires ingest_images records; must handle the window.confirm dialog; reprocessing requires ANTHROPIC_API_KEY for the agent pipeline to run, so the card may remain in an error state without it)
- **Priority**: medium

### recent_agent_trace_toggle
- **Description**: When I open the accordion for any card and click the bug icon button, the agent trace panel toggles visible. The trace shows OCR fragments with coordinates and confidence scores, Claude agent conversation steps (tool calls in orange, agent reasoning in blue, results in grey), and final JSON output in green. Clicking the bug icon again hides the trace.
- **References**: UX Description S4 User Flows > Flow 10, S3 Interactive Elements > Trace toggle button, .agent-trace
- **Testability**: limited (requires ingest_images records with populated agent_trace data; the --test fixture demo data may or may not include trace data)
- **Priority**: medium

### recent_done_card_overlays
- **Description**: Done cards in grid view display overlay elements: a Keyrune set icon in the bottom-left, a finish overlay or finish badges in the bottom-right, and a card title bar at the bottom with white text showing the card name and collector number. Foil cards have a rainbow shimmer animation overlay.
- **References**: UX Description S7 Visual States > Done State, S5 Dynamic Behavior > Card Element Updates, Foil Shimmer, Keyrune Set Icons
- **Testability**: limited (requires ingest_images records in done status; overlay content depends on the specific card data including set_code, collector_number, and finish)
- **Priority**: medium

### recent_table_mode_layout
- **Description**: In table view mode, card images are hidden and replaced by info-rows showing: card name (bold, white) with metadata (set icon, set code, collector number, finish), and side-by-side user photo and Scryfall thumbnail. Default columns are 3 on desktop. Grid-only overlays (set icon, finish badges, card title) are hidden on cards.
- **References**: UX Description S7 Visual States > Table/List View Mode, S5 Dynamic Behavior > Scryfall Thumbnails (Table Mode)
- **Testability**: limited (requires ingest_images records in done status; Scryfall thumbnails are lazy-loaded by fetching detail data for each card)
- **Priority**: medium

### Low Priority

### recent_usage_stats_display
- **Description**: The header displays a token usage box (#usage-box) showing estimated cost in bold (e.g., "~$0.0042") and token breakdown by model tier (haiku, sonnet, opus) with abbreviated counts. The stats refresh every 30 seconds. The box is hidden if no tokens have been used.
- **References**: UX Description S3 Interactive Elements > #usage-box, S5 Dynamic Behavior > On Page Load > loadUsageStats(), Polling > Usage stats polling, S7 Visual States > Usage Stats Display
- **Testability**: limited (requires images that have been processed through the Claude agent pipeline to generate usage data; if no processing has occurred, the usage box is hidden)
- **Priority**: low

### recent_processing_poll
- **Description**: When images are in the processing state (grey border), the page automatically polls their status every 3 seconds per image. When an image's status changes from processing, the poll stops for that image and the card updates in the grid with the new status and overlays.
- **References**: UX Description S4 User Flows > Flow 1 (step 5), S5 Dynamic Behavior > Polling > Per-image polling
- **Testability**: limited (requires an image actively being processed by the Claude agent pipeline, which needs ANTHROPIC_API_KEY and real-time processing; cannot be reliably tested with static fixture data alone)
- **Priority**: low

### recent_discovery_poll
- **Description**: The page runs a discovery poll (GET /api/ingest2/recent) every 20 seconds to detect new images uploaded from other tabs or devices. Newly discovered images are prepended to the grid.
- **References**: UX Description S5 Dynamic Behavior > Polling > Discovery polling
- **Testability**: limited (requires uploading an image from a separate session while the recent page is open; timing-dependent and hard to coordinate in automated tests)
- **Priority**: low

### recent_error_card_tooltip
- **Description**: Cards with error status display a large red "x" icon. On hover, an error tooltip appears at the bottom of the card showing the first 200 characters of the error message.
- **References**: UX Description S3 Interactive Elements > .error-tooltip, S7 Visual States > Error State
- **Testability**: limited (requires ingest_images records with error status and a non-empty error_message; hover interaction needed to trigger tooltip display)
- **Priority**: low

### recent_crop_zoom
- **Description**: Done cards apply crop zoom via CSS objectViewBox (inset) to focus on the detected card area of the uploaded photo, using crop coordinates provided by the server.
- **References**: UX Description S5 Dynamic Behavior > Crop Zoom
- **Testability**: limited (requires ingest_images records with populated crop coordinate data; visual verification of crop zoom requires comparing image styling)
- **Priority**: low

### recent_accordion_no_cards_detected
- **Description**: When I open the accordion for a card where no card was detected by OCR, the sidebar shows "No cards detected" as the title. Reprocess, Trace, and Delete buttons are available. Search inputs are available for manual card lookup. The candidate area shows "No candidates found. Try searching."
- **References**: UX Description S7 Visual States > Accordion "No Cards Detected" State
- **Testability**: limited (requires ingest_images records where OCR/agent processing completed but detected zero cards; uncommon scenario that may be hard to seed)
- **Priority**: low

### recent_accordion_already_ingested
- **Description**: When I open the accordion for a card that has already been ingested into the collection, the sidebar shows the card name with Reprocess, Trace, and Delete buttons, but the main area shows "Already ingested" text instead of candidates. No search inputs or "Add to Collection" button are visible.
- **References**: UX Description S7 Visual States > Accordion "Already Ingested" State
- **Testability**: limited (requires ingest_images records where the image has already been batch-ingested; can be set up by performing a batch ingest first, but image may be removed from grid rather than showing this state)
- **Priority**: low

### recent_view_mode_persistence
- **Description**: When I toggle between grid and table view, the choice is persisted to localStorage under the key "recent-view-mode". On page reload, the previously selected view mode is restored.
- **References**: UX Description S4 User Flows > Flow 11 (step 3), S5 Dynamic Behavior > On Page Load > applyViewMode()
- **Testability**: full (can set localStorage value via Playwright's page.evaluate and verify the view mode on page load; no data dependencies)
- **Priority**: low

### recent_accordion_show_all_candidates
- **Description**: When the candidate list in the accordion has been narrowed by the narrowing algorithm (filtering by matching artist, set code, collector number), a "Show all N candidates" button appears. Clicking it re-renders the full unfiltered candidate list.
- **References**: UX Description S5 Dynamic Behavior > Accordion Mechanics > Candidate narrowing, S3 Interactive Elements > "Show all N candidates" button
- **Testability**: limited (requires ingest_images records where the narrowing algorithm produces a strict subset of candidates; depends on Claude OCR metadata matching some but not all candidates)
- **Priority**: low

### recent_batch_ingest_with_assignment
- **Description**: When I select a deck or binder from the assign-target dropdown before clicking Batch Ingest, the assignment target is included in the batch ingest request. Ingested cards are assigned to the selected deck or binder in the collection.
- **References**: UX Description S4 User Flows > Flow 6 (step 2), S3 Interactive Elements > #assign-target
- **Testability**: limited (requires done ingest_images records plus existing decks/binders in the database; verifying the assignment requires checking the collection entries after ingest, which is an API-level concern)
- **Priority**: low

### recent_keyrune_fallback_map
- **Description**: Set codes with known Keyrune icon mismatches (tsb, pspm, cst) are correctly mapped to their fallback Keyrune class names (tsp, spm, csp) so that set icons display correctly.
- **References**: UX Description S5 Dynamic Behavior > Keyrune Set Icons
- **Testability**: limited (requires ingest_images records for cards from the specific sets with mismatched codes; niche scenario)
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| S1 Page Purpose | `recent_page_overview` (EXISTING), `recent_empty_state` |
| S2 Navigation > Header Links | `recent_navigation_header` |
| S2 Navigation > "Upload some photos" (empty state) | `recent_empty_state` |
| S2 Navigation > "Collection" link (batch msg) | `recent_batch_ingest` |
| S3 Interactive Elements > #usage-box | `recent_usage_stats_display` |
| S3 Interactive Elements > #col-minus, #col-plus, #col-count | `recent_column_adjust` |
| S3 Interactive Elements > #view-toggle | `recent_view_toggle` (EXISTING), `recent_view_mode_persistence` |
| S3 Interactive Elements > #assign-target | `recent_assign_target_dropdown`, `recent_batch_ingest_with_assignment` |
| S3 Interactive Elements > #batch-btn, #batch-msg | `recent_batch_ingest` |
| S3 Interactive Elements > .img-card | `recent_page_overview` (EXISTING), `recent_card_status_borders`, `recent_accordion_open_close` |
| S3 Interactive Elements > .finish-badge | `recent_finish_badge_quick_action` |
| S3 Interactive Elements > .error-tooltip | `recent_error_card_tooltip` |
| S3 Accordion Panel > Card title | `recent_accordion_open_close`, `recent_accordion_no_cards_detected` |
| S3 Accordion Panel > Reprocess button | `recent_reprocess_image` |
| S3 Accordion Panel > Trace toggle | `recent_agent_trace_toggle` |
| S3 Accordion Panel > Delete button | `recent_delete_image` |
| S3 Accordion Panel > "Add to Collection" button | `recent_single_card_ingest` |
| S3 Accordion Panel > Search inputs | `recent_search_alternative_card` |
| S3 Accordion Panel > .acc-candidate | `recent_accordion_candidate_select` |
| S3 Accordion Panel > "Show all N candidates" | `recent_accordion_show_all_candidates` |
| S3 Accordion Panel > .agent-trace | `recent_agent_trace_toggle` |
| S4 Flow 1: View Processing Status | `recent_page_overview` (EXISTING), `recent_status_summary_counts`, `recent_card_status_borders`, `recent_processing_poll` |
| S4 Flow 2: Inspect a Card (Accordion) | `recent_accordion_open_close` |
| S4 Flow 3: Correct a Card Identification | `recent_accordion_candidate_select` |
| S4 Flow 4: Search for an Alternative Card | `recent_search_alternative_card` |
| S4 Flow 5: Change Finish via Badge | `recent_finish_badge_quick_action` |
| S4 Flow 6: Batch Ingest All Done Cards | `recent_batch_ingest`, `recent_batch_ingest_with_assignment` |
| S4 Flow 7: Ingest a Single Card | `recent_single_card_ingest` |
| S4 Flow 8: Reprocess an Image | `recent_reprocess_image` |
| S4 Flow 9: Delete an Image | `recent_delete_image` |
| S4 Flow 10: View Agent Trace | `recent_agent_trace_toggle` |
| S4 Flow 11: Toggle View Mode | `recent_view_toggle` (EXISTING), `recent_view_mode_persistence` |
| S4 Flow 12: Adjust Column Count | `recent_column_adjust` |
| S5 Dynamic Behavior > On Page Load | `recent_page_overview` (EXISTING), `recent_status_summary_counts`, `recent_assign_target_dropdown`, `recent_view_mode_persistence` |
| S5 Dynamic Behavior > Polling > Per-image | `recent_processing_poll` |
| S5 Dynamic Behavior > Polling > Discovery | `recent_discovery_poll` |
| S5 Dynamic Behavior > Polling > Usage stats | `recent_usage_stats_display` |
| S5 Dynamic Behavior > Accordion Mechanics | `recent_accordion_open_close`, `recent_accordion_show_all_candidates` |
| S5 Dynamic Behavior > Card Element Updates | `recent_done_card_overlays`, `recent_accordion_candidate_select` |
| S5 Dynamic Behavior > Crop Zoom | `recent_crop_zoom` |
| S5 Dynamic Behavior > Foil Shimmer | `recent_done_card_overlays` |
| S5 Dynamic Behavior > Keyrune Set Icons | `recent_done_card_overlays`, `recent_keyrune_fallback_map` |
| S5 Dynamic Behavior > Scryfall Thumbnails (Table Mode) | `recent_table_mode_layout` |
| S7 Visual States > Empty State | `recent_empty_state` |
| S7 Visual States > Processing State | `recent_card_status_borders`, `recent_processing_poll` |
| S7 Visual States > Done State | `recent_card_status_borders`, `recent_done_card_overlays` |
| S7 Visual States > Needs Disambiguation State | `recent_card_status_borders` |
| S7 Visual States > Error State | `recent_card_status_borders`, `recent_error_card_tooltip` |
| S7 Visual States > Selected Card State | `recent_accordion_open_close` |
| S7 Visual States > Accordion Open State | `recent_accordion_open_close` |
| S7 Visual States > Accordion "Already Ingested" State | `recent_accordion_already_ingested` |
| S7 Visual States > Accordion "No Cards Detected" State | `recent_accordion_no_cards_detected` |
| S7 Visual States > Grid View Mode | `recent_page_overview` (EXISTING), `recent_done_card_overlays` |
| S7 Visual States > Table/List View Mode | `recent_view_toggle` (EXISTING), `recent_table_mode_layout` |
| S7 Visual States > Batch Ingest Success State | `recent_batch_ingest` |
| S7 Visual States > Usage Stats Display | `recent_usage_stats_display` |

---

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 8 | `recent_empty_state`, `recent_navigation_header`, `recent_status_summary_counts`, `recent_accordion_open_close`, `recent_batch_ingest`, `recent_delete_image`, `recent_card_status_borders`, `recent_single_card_ingest` |
| Medium | 8 | `recent_accordion_candidate_select`, `recent_search_alternative_card`, `recent_column_adjust`, `recent_assign_target_dropdown`, `recent_finish_badge_quick_action`, `recent_reprocess_image`, `recent_agent_trace_toggle`, `recent_done_card_overlays`, `recent_table_mode_layout` |
| Low | 10 | `recent_usage_stats_display`, `recent_processing_poll`, `recent_discovery_poll`, `recent_error_card_tooltip`, `recent_crop_zoom`, `recent_accordion_no_cards_detected`, `recent_accordion_already_ingested`, `recent_view_mode_persistence`, `recent_accordion_show_all_candidates`, `recent_batch_ingest_with_assignment`, `recent_keyrune_fallback_map` |

**Total new intents: 27** (plus 2 existing: `recent_page_overview`, `recent_view_toggle`)

---

## Testability Summary

| Testability | Count | Intents |
|---|---|---|
| Full | 4 | `recent_empty_state`, `recent_navigation_header`, `recent_column_adjust`, `recent_view_mode_persistence` |
| Limited | 25 | All remaining intents (both existing and new) |

## Testability Notes

The Recent/Process page is one of the most data-dependent pages in the application. Nearly all scenarios beyond the empty state and static UI elements require `ingest_images` records in the database with specific statuses and associated data (scryfall_matches, claude_result, agent_trace, crop coordinates, etc.). Key testability constraints:

1. **Ingest pipeline data**: Most scenarios require images that have been processed through the Claude Vision/OCR agent pipeline. The `--test` fixture includes demo ingest samples with `done` status, which enables testing of the accordion, candidate selection, batch ingest, and delete flows. However, `processing` and `needs_disambiguation` statuses may not be present without additional seeding.

2. **window.confirm dialogs**: The Reprocess and Delete actions use `window.confirm()` for confirmation. Playwright can handle these via `page.on('dialog')` event handlers, but this must be set up before triggering the action.

3. **Polling behavior**: Per-image polling (3s), discovery polling (20s), and usage stats polling (30s) are all timing-dependent. Testing polling transitions (processing -> done) requires either a running agent pipeline with `ANTHROPIC_API_KEY` or mock/seeded status changes, making these scenarios impractical for automated regression.

4. **Destructive actions**: Batch ingest, single-card ingest, delete, and reprocess all modify state. Tests exercising these flows must account for ordering (e.g., test inspection before deletion) or use separate fixture setups.

5. **External CDN dependencies**: Scryfall card images and Keyrune set icon fonts are loaded from CDNs. Tests running in network-isolated environments may see broken images or missing icons, which should not be treated as failures of the application logic.
