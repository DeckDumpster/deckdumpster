# Ingest Corners Page -- Approved Intents

Source: `tests/ui/ux-descriptions/ingest-corners.test-plan.md`

## Existing Coverage

- **`corners_ingest_deck_selector`** -- Deck dropdown lists existing decks, "Create new deck" option, inline deck creation, zone selector (Mainboard/Sideboard/Commander).
- **`corners_batch_browse`** -- Tests `/batches` page, not `/ingest-corners`.
- **`corners_batch_retroactive_deck_assign`** -- Tests `/batches` page, not `/ingest-corners`.

## Core Constraint

Nearly every flow on this page requires Claude Vision API calls (`POST /api/corners/detect`). Without `ANTHROPIC_API_KEY` configured and a real card corner image, the detection pipeline cannot produce results. This means:
- Camera capture flows are untestable (no `getUserMedia` in headless browsers).
- File upload detection flows are untestable (require Vision API + real images).
- Commit, discard, and remove-card flows all depend on having detection results first.

The only fully testable areas are static page structure, the New Session button, and deck selector interaction (already covered).

---

## Implement Now

### corners_page_initial_state
- **Description**: Verify the page loads with correct initial state: camera placeholder with "Open Camera" button visible (`#camera-btn`), drop zone visible with "Drop or select a photo of card corners" text, results section hidden, no messages, navigation links present (Home, Upload OCR, Collection, Batches, "New Session" button).
- **Testability**: Full -- no API calls needed. Pure DOM element visibility checks.
- **Why now**: Validates the page loads correctly and all initial elements are in the right state. Zero dependencies.

### corners_new_session
- **Description**: Click the "New Session" button in the header. Verify state is cleared: results section hidden, messages cleared, photo counter reset. A "New session started" green success message appears.
- **Testability**: Full -- no external dependencies. Click and verify DOM state changes.
- **Why now**: Testable without any Vision API or camera. Validates session management UI.

---

## Deferred

### corners_file_upload_detection
- **Reason**: Requires Claude Vision API (`POST /api/corners/detect`). The test harness does not have `ANTHROPIC_API_KEY` configured, and even if it did, Vision calls are expensive (~$0.01-0.03 per call) and non-deterministic. Cannot produce stable test results.

### corners_commit_cards
- **Reason**: Depends on detection results being present. Could theoretically be tested by injecting `currentCards` state via `page.evaluate()`, but this is fragile (depends on internal JS variable names) and tests implementation details rather than user-facing behavior.

### corners_discard_results
- **Reason**: Same as `corners_commit_cards` -- requires detection results or JS state injection.

### corners_remove_individual_card
- **Reason**: Same dependency on detection results.

### corners_create_deck_during_ingest
- **Reason**: The deck creation flow is already covered by `corners_ingest_deck_selector`. The proposed extension (full create-and-cancel cycle within active results context) requires detection results to be displayed first.

### corners_deck_assignment_commit
- **Reason**: Requires detection results to be displayed for the commit to be meaningful.

### corners_detection_error_states
- **Reason**: Requires specific API responses from the Vision detection pipeline. Sending a blank image might work, but the server returns 503 without `ANTHROPIC_API_KEY`.

### corners_message_auto_removal
- **Reason**: Could be tested using "New Session" to trigger a message, then waiting 10 seconds. However, 10-second waits are slow and timing-dependent. Low ROI.

### corners_drop_zone_drag_visual
- **Reason**: Drag-and-drop event simulation is unreliable in Playwright. CSS state changes during dragover are transient and hard to capture.

### corners_camera_open_close
- **Reason**: Camera APIs (`getUserMedia`) are not available in headless browser environments. The camera permission prompt cannot be automated.

### corners_photo_counter_badge
- **Reason**: Depends on camera capture working, which is blocked by headless browser limitations.

### corners_api_key_missing
- **Reason**: Requires a server instance specifically configured without `ANTHROPIC_API_KEY`. Not practical for standard test runs.
