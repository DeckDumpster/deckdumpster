# Order Import Page -- Approved Intents

Source: `tests/ui/ux-descriptions/ingestor-order.test-plan.md`

## Existing Coverage

- **`order_import_parse_and_review`** -- Paste order text, click Parse, see resolved results grouped by seller with card thumbnails, set, and collector number.
- **`order_import_unresolved_cards`** -- Parse order with cards not in DB; verify red error styling and "Failed" count in summary bar.

## Core Advantage

Parsing and resolution use local logic and the local Scryfall database -- no external API calls. The main requirement is realistic sample order text that references cards in the fixture DB.

---

## Implement Now

### order_page_initial_state
- **Description**: Verify the page loads with correct initial state: empty textarea with placeholder "Paste TCGPlayer/CK order text here...", drop zone with "Click or drop .html / .txt files" text and dashed border, "Ordered" pill active by default, "Owned" pill inactive, format dropdown set to "Auto-detect" with all 5 options (Auto-detect, TCGPlayer HTML, TCGPlayer Text, Card Kingdom HTML, Card Kingdom Text), results panel showing info message "Paste order data or upload files, then click Parse." Home link present.
- **Testability**: Full -- no API calls needed.
- **Why now**: Validates the page contract. Pure DOM assertions.
- **Note**: Absorbs the proposed `order_format_selection` -- the format dropdown options are verified as part of initial state.

### order_status_toggle
- **Description**: Click "Owned" pill to activate it, verify "Ordered" deactivates (loses `.active` class). Click "Ordered" to switch back. Verify active pill has red background, inactive has dark background.
- **Testability**: Full -- pure CSS class toggling.
- **Why now**: Status toggle is a unique UI element on this page. No data dependencies.

### order_no_input_error
- **Description**: Click Parse with empty textarea and no files. Verify error message "No input provided." appears in results panel.
- **Testability**: Full -- simple validation check.
- **Why now**: Input validation is a basic UX contract. One click, one assertion.

### order_no_orders_found
- **Description**: Paste random/garbage text (not a recognized order format), click Parse. Verify error message "No orders found in input." appears.
- **Testability**: Full -- paste nonsense, click Parse, check error.
- **Why now**: Validates the parser's error path. Simple.

### order_parse_and_commit
- **Description**: Paste valid TCGPlayer-format order text containing cards that exist in the fixture DB. Click Parse. Verify the two-step pipeline: "Parsing orders..." then "Resolving cards..." progress messages. Verify resolved results show order groups with seller info, item tables with card thumbnails, set, condition, qty, price. Click "Add All to Collection". Verify success message with card/order counts.
- **Testability**: Testable -- requires sample order text referencing fixture DB cards. Parse and resolve use local logic.
- **Why now**: End-to-end happy path. The most important flow on the page.
- **Note**: Will need fixture order text data. The test implementation should embed a minimal TCGPlayer text order referencing known cards (e.g., "Lightning Bolt" from a set in the fixture).

### order_cancel_after_resolve
- **Description**: Parse a valid order, then click Cancel. Verify results panel shows "Cancelled. Paste new data to start over." and resolved data is cleared.
- **Testability**: Full -- requires a successful parse first.
- **Why now**: Cancel is a standard interaction. Simple assertion.

### order_commit_ordered_guidance
- **Description**: Parse an order with "Ordered" status selected (the default), commit. Verify that in addition to the green success message, an amber/gold guidance message appears directing the user to the Collection page to mark cards as received. Verify the message includes a link to `/collection`.
- **Testability**: Testable -- requires valid order text and successful commit.
- **Why now**: The "Ordered" guidance is a unique UX element specific to this page. Important to verify it appears when expected and contains the correct link.

### order_assign_to_deck
- **Description**: After resolving an order, verify the assign target dropdown has optgroups for Decks (Bolt Tribal, Eldrazi Ramp) and Binders (Trade Binder, Foil Collection) with `deck:ID` / `binder:ID` values. Select a deck, commit, verify success.
- **Testability**: Testable -- fixture has decks and binders.
- **Why now**: Assignment dropdown is a shared pattern across pages, but must be verified here.

---

## Deferred

### order_format_selection
- **Reason**: Merged into `order_page_initial_state`. The dropdown options are verified there.

### order_file_upload
- **Reason**: File upload via Playwright file input injection is testable, but requires sample HTML order files as fixture data that do not exist yet. Defer until fixture files are created.

### order_drag_and_drop_visual
- **Reason**: Drag-and-drop simulation in Playwright is unreliable. CSS state changes during dragover are transient and hard to capture.

### order_commit_error
- **Reason**: Difficult to trigger reliably without server-side manipulation or network interception.

### order_multiple_files_concat
- **Reason**: Requires multiple sample order files. Depends on `order_file_upload` being implemented first.

### order_mobile_layout
- **Reason**: Viewport manipulation for visual validation. Low priority.

### order_card_kingdom_format
- **Reason**: Requires Card Kingdom sample data fixtures that do not exist yet. The parser logic is format-specific but the UI behavior is identical regardless of format. Defer until CK fixtures are available.
