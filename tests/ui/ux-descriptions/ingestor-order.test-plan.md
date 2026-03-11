# Test Plan: Order Import Page (`/ingestor-order`)

## 1. Existing Intents

| Intent File | Summary |
|-------------|---------|
| `order_import_parse_and_review.yaml` | Paste order text into the Order Ingestion page, click Parse, and see resolved results grouped by seller with card thumbnails, set, and collector number information. |
| `order_import_unresolved_cards.yaml` | Parse an order containing cards that cannot be found in the database; verify unresolved cards appear with red error styling and a "Failed" count in the summary bar. |

---

## 2. Proposed New Intents

### High Priority

#### `order_page_initial_state.yaml`
- **Description:** Verify the Order Import page loads with correct initial state: empty textarea with placeholder text, drop zone with "Click or drop .html / .txt files" text and dashed border, "Ordered" pill active by default, "Owned" pill inactive, format dropdown set to "Auto-detect", results panel showing info message "Paste order data or upload files, then click Parse." Navigation link to Home present.
- **Priority:** High
- **UX Flows/States Covered:** On Page Load, Input Panel State (Empty), Results Panel State (Initial), Section 2 (Navigation), Status Pill Toggle (default state)
- **Testability Notes:** Fully testable. No API calls needed. Verify DOM elements, placeholder text, and pill states.

#### `order_parse_and_commit.yaml`
- **Description:** Paste valid order text (TCGPlayer format), click Parse, wait for the two-step parse+resolve pipeline, verify the results panel shows order groups with seller info and item tables. Then click "Add All to Collection" and verify the success message with card/order counts and the state resets.
- **Priority:** High
- **UX Flows/States Covered:** Flow 1 (Paste Order Text and Parse), Flow 5 (Assign to Deck/Binder and Commit), Results Panel States (Parsing, Resolving, Resolved, Committing, Commit success Owned)
- **Testability Notes:** Testable. Requires valid order text that matches cards in the test fixture database. The parse and resolve endpoints use local parsing logic and local DB -- no external APIs. Need sample TCGPlayer order text as fixture data.

#### `order_status_toggle.yaml`
- **Description:** Verify the status pill toggle behavior: click "Owned" to activate it and verify "Ordered" deactivates. Click "Ordered" to switch back. Verify the active pill has red background styling and the inactive pill has dark background.
- **Priority:** High
- **UX Flows/States Covered:** Flow 7 (Toggle Order Status), Status Pill Toggle
- **Testability Notes:** Fully testable. Pure CSS class toggling. Click pills and verify `.active` class membership.

#### `order_commit_ordered_guidance.yaml`
- **Description:** Parse an order with "Ordered" status selected, commit, and verify that in addition to the success message, an amber/gold guidance message appears directing the user to the Collection page to mark cards as received. Verify the guidance message includes a link to `/collection`.
- **Priority:** High
- **UX Flows/States Covered:** Flow 5 step 6 (Ordered guidance), Results Panel State (Commit success Ordered), Ordered vs Owned Guidance
- **Testability Notes:** Testable. Requires valid order text. Verify the amber message content and link target after commit.

### Medium Priority

#### `order_file_upload.yaml`
- **Description:** Click the file drop zone, select HTML/TXT files via the file input, and verify: filenames appear in the drop zone text, border turns green (`.has-files` class), and file contents populate the textarea. Then click Parse and verify normal resolution flow.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 2 (Upload HTML Files and Parse), Input Panel State (Files loaded), File Upload Handling
- **Testability Notes:** Testable via Playwright file input injection. Requires sample HTML order files as fixture data. The drag-and-drop visual feedback (Flow 3) is harder to test.

#### `order_no_input_error.yaml`
- **Description:** Click Parse with an empty textarea and no files loaded. Verify the error message "No input provided." appears in the results panel.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 1 step 5 (empty input validation), Results Panel State (No input error)
- **Testability Notes:** Fully testable. Click Parse with empty state and verify error message.

#### `order_no_orders_found.yaml`
- **Description:** Paste text that is not a recognized order format (e.g., random text) and click Parse. Verify the error message "No orders found in input." appears.
- **Priority:** Medium
- **UX Flows/States Covered:** Results Panel State (No orders found)
- **Testability Notes:** Fully testable. Paste garbage text and verify the parse endpoint returns no orders.

#### `order_cancel_after_resolve.yaml`
- **Description:** Parse a valid order, then click Cancel in the action bar. Verify the results panel shows "Cancelled. Paste new data to start over." and resolved data is cleared.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 6 (Cancel After Resolution), Results Panel State (Cancelled)
- **Testability Notes:** Fully testable. Requires a successful parse first.

#### `order_assign_to_deck.yaml`
- **Description:** After parsing and resolving an order, select a deck from the assign target dropdown and commit. Verify the deck assignment is included in the commit payload and the success message reflects the assignment.
- **Priority:** Medium
- **UX Flows/States Covered:** Flow 5 (Assign to Deck/Binder and Commit), Assign Target Loading
- **Testability Notes:** Testable if decks exist in the test fixture. Verify dropdown has optgroups for Decks and Binders with `deck:ID` / `binder:ID` values.

#### `order_format_selection.yaml`
- **Description:** Verify the format dropdown includes all expected options (Auto-detect, TCGPlayer HTML, TCGPlayer Text, Card Kingdom HTML, Card Kingdom Text). Select a specific format before parsing and verify it is sent with the parse request.
- **Priority:** Medium
- **UX Flows/States Covered:** Format dropdown, Flow 1 step 2 (format selection)
- **Testability Notes:** Fully testable for verifying dropdown options. Testing that the selected format affects parsing requires format-specific sample data.

### Low Priority

#### `order_drag_and_drop_visual.yaml`
- **Description:** Drag a file over the drop zone and verify the border changes to red (#e94560) on dragover. Drop the file and verify the border resets and filenames appear with green border.
- **Priority:** Low
- **UX Flows/States Covered:** Flow 3 (Drag and Drop Files), File Upload Handling (visual feedback)
- **Testability Notes:** LIMITED TESTABILITY. Drag-and-drop simulation in Playwright is unreliable. The dragover/dragleave CSS changes are difficult to assert programmatically. JavaScript event dispatch could work for functional testing but not visual verification.

#### `order_commit_error.yaml`
- **Description:** Trigger a commit failure and verify a red error message appears and the commit button re-enables with "Add All to Collection" text.
- **Priority:** Low
- **UX Flows/States Covered:** Results Panel State (Commit error)
- **Testability Notes:** Difficult to trigger reliably without server-side manipulation or network interception.

#### `order_multiple_files_concat.yaml`
- **Description:** Upload multiple files via the drop zone and verify all file contents are concatenated in the textarea with newline separators. Verify the drop zone shows comma-separated filenames.
- **Priority:** Low
- **UX Flows/States Covered:** File Upload Handling (multiple files), Flow 2
- **Testability Notes:** Testable via Playwright multi-file input. Requires multiple sample order files.

#### `order_mobile_layout.yaml`
- **Description:** Verify the mobile layout: single-column with input panel stacking above results panel, textarea constrained to 80-120px height, smaller font/padding in item tables, thumbnails at 24x33px.
- **Priority:** Low
- **UX Flows/States Covered:** Layout States (Mobile <= 768px)
- **Testability Notes:** Testable with viewport resizing. Requires screenshot comparison for visual validation.

#### `order_card_kingdom_format.yaml`
- **Description:** Paste Card Kingdom order text (or upload CK HTML), select "Card Kingdom Text" (or "Card Kingdom HTML") format, parse, and verify resolution works correctly with CK-specific seller names and formatting.
- **Priority:** Low
- **UX Flows/States Covered:** Flow 1 with Card Kingdom format, Format auto-detection
- **Testability Notes:** Testable if CK sample data is available. Tests the parser's format detection and CK-specific parsing logic.

---

## 3. Coverage Matrix

| UX Description Section | Existing Intents | Proposed Intents |
|------------------------|-----------------|-----------------|
| **Navigation (Section 2)** | -- | `order_page_initial_state` |
| **Order text textarea (Section 3)** | `order_import_parse_and_review` (implicit) | `order_page_initial_state`, `order_parse_and_commit` |
| **File upload drop zone (Section 3)** | -- | `order_file_upload`, `order_drag_and_drop_visual` (limited) |
| **Format dropdown (Section 3)** | -- | `order_format_selection`, `order_card_kingdom_format` |
| **Status pills (Section 3)** | -- | `order_status_toggle`, `order_commit_ordered_guidance` |
| **Parse button (Section 3)** | `order_import_parse_and_review` | `order_no_input_error`, `order_no_orders_found` |
| **Assign target dropdown (Section 3)** | -- | `order_assign_to_deck` |
| **Commit button (Section 3)** | -- | `order_parse_and_commit`, `order_commit_ordered_guidance` |
| **Cancel button (Section 3)** | -- | `order_cancel_after_resolve` |
| **Flow 1: Paste and Parse** | `order_import_parse_and_review` | `order_parse_and_commit`, `order_no_input_error`, `order_no_orders_found` |
| **Flow 2: Upload Files** | -- | `order_file_upload` |
| **Flow 3: Drag and Drop** | -- | `order_drag_and_drop_visual` (limited) |
| **Flow 4: Review Resolved** | `order_import_parse_and_review`, `order_import_unresolved_cards` | `order_parse_and_commit` |
| **Flow 5: Assign and Commit** | -- | `order_parse_and_commit`, `order_assign_to_deck`, `order_commit_ordered_guidance` |
| **Flow 6: Cancel** | -- | `order_cancel_after_resolve` |
| **Flow 7: Toggle Status** | -- | `order_status_toggle` |
| **State: Initial** | -- | `order_page_initial_state` |
| **State: Text pasted** | `order_import_parse_and_review` (implicit) | -- |
| **State: Files loaded** | -- | `order_file_upload` |
| **State: Parsing** | `order_import_parse_and_review` (implicit) | `order_parse_and_commit` |
| **State: No input error** | -- | `order_no_input_error` |
| **State: Parsing spinner** | -- | `order_parse_and_commit` |
| **State: No orders found** | -- | `order_no_orders_found` |
| **State: Resolving** | -- | `order_parse_and_commit` |
| **State: Resolved (all)** | `order_import_parse_and_review` | `order_parse_and_commit` |
| **State: Resolved (mixed)** | `order_import_unresolved_cards` | -- |
| **State: Network/API error** | -- | -- (not practically testable) |
| **State: Committing** | -- | `order_parse_and_commit` |
| **State: Commit success (Owned)** | -- | `order_parse_and_commit` |
| **State: Commit success (Ordered)** | -- | `order_commit_ordered_guidance` |
| **State: Commit error** | -- | `order_commit_error` |
| **State: Cancelled** | -- | `order_cancel_after_resolve` |
| **Layout: Desktop** | `order_import_parse_and_review` (implicit) | -- |
| **Layout: Mobile** | -- | `order_mobile_layout` |
| **Two-step parse+resolve** | `order_import_parse_and_review` (implicit) | `order_parse_and_commit` |
| **Ordered vs Owned guidance** | -- | `order_commit_ordered_guidance` |
| **Assign target optgroups** | -- | `order_assign_to_deck` |
| **Card Kingdom format** | -- | `order_card_kingdom_format` |

### Testability Summary

The Order Import page is well-suited for automated testing because parsing and resolution use local logic and the local database -- no external API calls. The main challenge is providing realistic order text fixtures.

- **Fully testable:** `order_page_initial_state`, `order_status_toggle`, `order_no_input_error`, `order_no_orders_found`, `order_cancel_after_resolve`, `order_format_selection`
- **Testable with fixture data:** `order_parse_and_commit`, `order_commit_ordered_guidance`, `order_file_upload`, `order_assign_to_deck`, `order_card_kingdom_format`, `order_multiple_files_concat`
- **Testable with viewport manipulation:** `order_mobile_layout`
- **Limited testability:** `order_drag_and_drop_visual` (drag-and-drop simulation)
- **Difficult to trigger:** `order_commit_error` (requires server-side failure)

### Coverage Gaps

- **File upload flow** has no existing coverage at all. Neither existing intent tests HTML file upload or drag-and-drop.
- **Status pill toggle** ("Ordered" vs "Owned") has no existing coverage. The "Ordered" guidance message after commit is also uncovered.
- **Commit flow** is entirely uncovered -- no existing intent verifies the full parse-to-commit cycle or success/error states.
- **Cancel flow** is uncovered.
- **Format-specific parsing** (Card Kingdom vs TCGPlayer, HTML vs Text) has no existing coverage. Both existing intents likely use a single format.
- **Assign target** (deck/binder dropdown) behavior during order import has no existing coverage.
- **Multiple file concatenation** has no coverage.
