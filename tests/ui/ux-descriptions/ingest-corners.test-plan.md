# Test Plan: Ingest Corners Page (`/ingest-corners`)

## 1. Existing Intents

| Intent File | Summary |
|-------------|---------|
| `corners_batch_browse.yaml` | Navigate to corner batches page, view past batches with date/count/deck, click into a batch to see card thumbnails and names. |
| `corners_batch_retroactive_deck_assign.yaml` | From the batches page, select an unassigned batch and assign it to an existing deck; verify the deck name appears in the list and cards appear in the deck. |
| `corners_ingest_deck_selector.yaml` | On the ingest corners page, verify the deck selector dropdown lists existing decks and the "Create new deck" option. Create a new deck inline and confirm it appears in the dropdown. Verify the zone selector (Mainboard/Sideboard/Commander). |

Note: `corners_batch_browse` and `corners_batch_retroactive_deck_assign` test the `/batches` page functionality rather than the `/ingest-corners` page itself. Only `corners_ingest_deck_selector` directly tests the ingest corners page.

---

## 2. Proposed New Intents

### High Priority

#### `corners_page_initial_state.yaml`
- **Description:** Verify the ingest corners page loads with the correct initial state: camera placeholder with "Open Camera" button visible, drop zone visible with correct prompt text, results section hidden, no messages, and navigation links present.
- **Priority:** High
- **UX Flows/States Covered:** State 1 (Initial / Camera Closed), Section 2 (Navigation), On Page Load behavior
- **Testability Notes:** Fully testable. Load the page and verify element visibility via selectors (`#camera-placeholder`, `#camera-btn`, `#drop-zone`, `#results-section`). No camera or file upload needed.

#### `corners_file_upload_detection.yaml`
- **Description:** Upload an image file via the drop zone (programmatic file input) and verify the processing spinner appears, then results are displayed in the table with card name, set/CN, rarity, foil toggle, condition dropdown, and remove button. Verify the deck selector becomes visible.
- **Priority:** High
- **UX Flows/States Covered:** Flow 2 (File Upload via Drop Zone), State 4 (Processing), State 5 (Results Displayed), Detection Pipeline, Results Rendering
- **Testability Notes:** LIMITED TESTABILITY. Requires a real image of card corners and a working Claude Vision API key on the server. The detect endpoint calls Claude Vision, which is expensive and non-deterministic. Could use a mock/fixture image that produces known results if the server supports test mode. File upload can be driven via Playwright file input injection.

#### `corners_commit_cards.yaml`
- **Description:** After detection results are displayed, click "Add to Collection" and verify the button shows "Adding..." while disabled, then a success message appears with card names, and the results section hides.
- **Priority:** High
- **UX Flows/States Covered:** Flow 1 steps 14-16, State 8 (Commit In Progress), State 9 (Commit Success), Commit Flow
- **Testability Notes:** LIMITED TESTABILITY. Depends on having detection results first, which requires Claude Vision. Could be tested if the test harness can inject `currentCards` state via JavaScript before clicking commit.

#### `corners_discard_results.yaml`
- **Description:** After detection results are displayed, click the "Discard" button and verify all cards are cleared, the results section hides, and no confirmation dialog appears.
- **Priority:** High
- **UX Flows/States Covered:** Flow 8 (Discard All Results), State 1/2 return
- **Testability Notes:** LIMITED TESTABILITY. Same dependency on having results displayed first. Could be tested with injected state.

### Medium Priority

#### `corners_remove_individual_card.yaml`
- **Description:** With multiple cards in the results table, click the remove button on one card and verify it is removed from the table, the count updates, and the remaining cards stay. Then remove all cards one by one and verify the results section hides entirely.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 7 (Remove Individual Card from Results), State 13 (Empty Results After Removal)
- **Testability Notes:** LIMITED TESTABILITY. Requires detection results. Could use injected state.

#### `corners_new_session.yaml`
- **Description:** Click the "New Session" button in the header and verify state is cleared: results section hidden, messages cleared, photo counter reset. A "New session started" success message should appear and auto-remove after ~10 seconds.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 9 (Start New Session), State 15 (New Session Started), Session Management
- **Testability Notes:** Fully testable. No external dependencies. Click the button and verify DOM state changes.

#### `corners_create_deck_during_ingest.yaml`
- **Description:** With results displayed, select "+ Create new deck..." from the deck dropdown, verify the new deck form appears with name input and format dropdown. Enter a name, click Create, and verify the new deck is auto-selected in the dropdown and the form hides. Then cancel a second creation attempt and verify the dropdown resets to "None".
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 5 (Create New Deck During Ingest), Flow 6 (Cancel New Deck), State 7 (New Deck Form Open)
- **Testability Notes:** Partially covered by `corners_ingest_deck_selector`. This intent extends coverage to the full create-and-cancel cycle within the context of active results. Requires results to be displayed first.

#### `corners_deck_assignment_commit.yaml`
- **Description:** With results displayed, select an existing deck from the dropdown, choose a zone (e.g., Sideboard), click "Add to Collection", and verify the success message includes the deck name.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 4 (Assign to Existing Deck), State 6 (Results with Deck Selected)
- **Testability Notes:** LIMITED TESTABILITY. Requires detection results and an existing deck. Deck selector portion is testable; full commit requires Vision results.

#### `corners_detection_error_states.yaml`
- **Description:** Verify error handling: when detection returns no cards, a specific error message appears ("No cards detected..."). When skipped cards are returned, a skipped info banner appears with count. When a network error occurs, an appropriate red error message displays.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 11 (Skipped Cards), State 10 (Detection Error), State 11 (Partial Detection with Skipped Cards), State 14 (Network Error)
- **Testability Notes:** LIMITED TESTABILITY. Requires specific API responses. Could be tested by sending an image that produces no detections, or by intercepting network requests. Network error could be simulated by stopping the server mid-request.

### Low Priority

#### `corners_message_auto_removal.yaml`
- **Description:** Trigger a success message and verify it auto-removes after approximately 10 seconds.
- **Priority:** Low
- **UX Flows/States Covered:** Message System (auto-removal behavior)
- **Testability Notes:** Testable with a timer-based assertion, but requires waiting ~10 seconds which is slow for a test. Could use the "New Session" button to trigger a message without needing Vision.

#### `corners_drop_zone_drag_visual.yaml`
- **Description:** Verify that dragging a file over the drop zone changes the border from dashed blue to dashed red with a subtle red tint, and reverting on drag leave.
- **Priority:** Low
- **UX Flows/States Covered:** State 12 (Drop Zone Drag Hover)
- **Testability Notes:** LIMITED TESTABILITY. Drag-and-drop events are difficult to simulate reliably in Playwright. CSS state changes on dragover could potentially be triggered via JavaScript event dispatch, but visual verification requires screenshot comparison.

#### `corners_camera_open_close.yaml`
- **Description:** Click "Open Camera" and verify the camera placeholder hides and camera controls appear. Click "Close Camera" and verify the camera view hides and placeholder returns.
- **Priority:** Low
- **UX Flows/States Covered:** Flow 1 steps 2-3, State 2 (Camera Active), Camera Lifecycle (startCamera/stopCamera)
- **Testability Notes:** LIMITED TESTABILITY. Camera APIs (`getUserMedia`) are not available in headless browser environments. The camera permission prompt cannot be automated. The fallback path (no `getUserMedia`) could be tested but requires a browser that lacks the API.

#### `corners_photo_counter_badge.yaml`
- **Description:** After capturing a photo, verify the photo count badge appears showing "1 captured" and increments with subsequent captures.
- **Priority:** Low
- **UX Flows/States Covered:** State 3 (Camera Active with Captures), Photo count badge behavior
- **Testability Notes:** LIMITED TESTABILITY. Depends on camera capture working, which is blocked by camera API limitations in headless mode.

#### `corners_api_key_missing.yaml`
- **Description:** On a server without ANTHROPIC_API_KEY, attempt detection and verify the error message "ANTHROPIC_API_KEY not set -- corner detection requires an API key" appears.
- **Priority:** Low
- **UX Flows/States Covered:** State 16 (API Key Missing)
- **Testability Notes:** Requires a specially configured server instance without the API key. Not practical for standard test runs.

---

## 3. Coverage Matrix

| UX Description Section | Existing Intents | Proposed Intents |
|------------------------|-----------------|-----------------|
| **Navigation (Section 2)** | `corners_ingest_deck_selector` (partial) | `corners_page_initial_state` |
| **Camera Section (Section 3)** | -- | `corners_camera_open_close` (limited), `corners_photo_counter_badge` (limited) |
| **File Upload Section (Section 3)** | -- | `corners_file_upload_detection` (limited), `corners_drop_zone_drag_visual` (limited) |
| **Processing Indicator (Section 3)** | -- | `corners_file_upload_detection` (limited) |
| **Messages Area (Section 3)** | -- | `corners_message_auto_removal`, `corners_detection_error_states` (limited) |
| **Results Table (Section 3)** | -- | `corners_file_upload_detection` (limited), `corners_remove_individual_card` (limited) |
| **Foil/Condition per card (Section 3)** | -- | `corners_file_upload_detection` (limited) |
| **Deck Assignment (Section 3)** | `corners_ingest_deck_selector` | `corners_create_deck_during_ingest`, `corners_deck_assignment_commit` (limited) |
| **Action Buttons (Section 3)** | -- | `corners_commit_cards` (limited), `corners_discard_results` (limited) |
| **Session Management (Section 3)** | -- | `corners_new_session` |
| **Flow 1: Camera Capture** | -- | `corners_camera_open_close` (limited), `corners_photo_counter_badge` (limited) |
| **Flow 2: File Upload** | -- | `corners_file_upload_detection` (limited) |
| **Flow 3: Camera Fallback** | -- | -- (not practically testable) |
| **Flow 4: Assign to Existing Deck** | `corners_ingest_deck_selector` (partial) | `corners_deck_assignment_commit` (limited) |
| **Flow 5: Create New Deck** | `corners_ingest_deck_selector` | `corners_create_deck_during_ingest` |
| **Flow 6: Cancel New Deck** | -- | `corners_create_deck_during_ingest` |
| **Flow 7: Remove Individual Card** | -- | `corners_remove_individual_card` (limited) |
| **Flow 8: Discard All** | -- | `corners_discard_results` (limited) |
| **Flow 9: New Session** | -- | `corners_new_session` |
| **Flow 10: Multiple Captures** | -- | -- (limited by camera API) |
| **Flow 11: Skipped Cards** | -- | `corners_detection_error_states` (limited) |
| **State 1: Initial** | -- | `corners_page_initial_state` |
| **State 2: Camera Active** | -- | `corners_camera_open_close` (limited) |
| **State 3: Camera with Captures** | -- | `corners_photo_counter_badge` (limited) |
| **State 4: Processing** | -- | `corners_file_upload_detection` (limited) |
| **State 5: Results Displayed** | -- | `corners_file_upload_detection` (limited) |
| **State 6: Deck Selected** | `corners_ingest_deck_selector` (partial) | `corners_deck_assignment_commit` (limited) |
| **State 7: New Deck Form** | `corners_ingest_deck_selector` | `corners_create_deck_during_ingest` |
| **State 8: Commit In Progress** | -- | `corners_commit_cards` (limited) |
| **State 9: Commit Success** | -- | `corners_commit_cards` (limited) |
| **State 10: Detection Error** | -- | `corners_detection_error_states` (limited) |
| **State 11: Partial with Skipped** | -- | `corners_detection_error_states` (limited) |
| **State 12: Drag Hover** | -- | `corners_drop_zone_drag_visual` (limited) |
| **State 13: Empty After Removal** | -- | `corners_remove_individual_card` (limited) |
| **State 14: Network Error** | -- | `corners_detection_error_states` (limited) |
| **State 15: New Session** | -- | `corners_new_session` |
| **State 16: API Key Missing** | -- | `corners_api_key_missing` |

### Testability Summary

The ingest corners page is heavily dependent on Claude Vision for its core detection flow, which makes most end-to-end scenarios expensive and non-deterministic. The most practically testable intents are:

- **Fully testable:** `corners_page_initial_state`, `corners_new_session`, `corners_message_auto_removal`
- **Testable with JS state injection:** `corners_commit_cards`, `corners_discard_results`, `corners_remove_individual_card`, `corners_create_deck_during_ingest`, `corners_deck_assignment_commit`
- **Limited by external dependencies:** `corners_file_upload_detection`, `corners_detection_error_states`, `corners_camera_open_close`, `corners_photo_counter_badge`, `corners_drop_zone_drag_visual`, `corners_api_key_missing`
- **Not practically testable:** Flow 3 (Camera Fallback), Flow 10 (Multiple Captures in session)

### Coverage Gaps

- **Camera flows** are largely untestable in headless environments. No existing intents cover camera behavior.
- **Detection pipeline end-to-end** requires Claude Vision API calls, making full integration tests expensive. No existing intents cover the detect-review-commit cycle.
- **Error state coverage** is absent -- no existing intents test error messages, skipped cards, or network failures.
