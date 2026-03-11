# CSV Import Page -- Approved Intents

Source: `tests/ui/ux-descriptions/import-csv.test-plan.md`

## Existing Coverage

- **`csv_import_with_batch_metadata`** -- Verifies presence of batch metadata fields: batch name input, product type dropdown, set code input.

## Core Advantage

Parsing and resolution use local logic and the local Scryfall database -- no external API calls. The page supports multiple CSV formats (Moxfield, Archidekt, Deckbox) and plain text deck lists. Plain text deck lists (e.g., "1 Lightning Bolt") are the easiest to construct inline without fixture files.

---

## Implement Now

### csv_import_page_structure
- **Description**: Verify the page loads with correct initial state: page title "CSV Import", "<-- Home" link in header, two-panel layout with left input panel containing: monospace textarea with placeholder "Paste CSV here (e.g. Moxfield deck export)...", file upload drop zone with dashed border and "Or drop/click to upload a .csv file" text, format dropdown defaulting to "Auto-detect" with all 5 options (Auto-detect, Deck List (text), Moxfield (CSV), Archidekt (CSV), Deckbox (CSV)), batch metadata fields, and "Parse & Resolve" button. Right results panel shows info message "Paste a CSV export or upload a file, then click Parse & Resolve."
- **Testability**: Full -- no API calls needed.
- **Why now**: Validates the complete page contract. Pure DOM assertions.
- **Note**: Absorbs `csv_import_format_dropdown_options` and `csv_import_home_link_navigation` and `csv_import_product_type_options`. All three are simple element-existence checks that belong in a single page structure verification.

### csv_import_parse_empty_input
- **Description**: Click "Parse & Resolve" without entering text or uploading a file. Verify red error message "No CSV text provided." appears.
- **Testability**: Full -- simple validation check.
- **Why now**: Input validation is a basic UX contract.

### csv_import_parse_and_resolve_decklist
- **Description**: Paste a plain text deck list (e.g., "1 Lightning Bolt\n2 Counterspell\n4 Sol Ring") into the textarea, click "Parse & Resolve". Verify the two-step pipeline completes: summary bar shows total cards, resolved count, and detected format. Resolved cards appear in table with Card (thumbnail + name), Set/CN, Condition, Qty columns. Action bar appears with "Add to Collection", "Cancel", and assign target dropdown.
- **Testability**: Full -- deck list format uses simple "N CardName" syntax. Cards must exist in fixture DB.
- **Why now**: End-to-end parse+resolve happy path. The most important flow.

### csv_import_commit_to_collection
- **Description**: After resolving cards, click "Add to Collection". Verify button shows "Adding..." while disabled. On success, green message "Successfully added N card(s) to collection." appears. Only resolved cards are committed.
- **Testability**: Full -- follows naturally from parse_and_resolve.
- **Why now**: Commit is the workflow completion step. Must verify end-to-end.

### csv_import_failed_cards_display
- **Description**: Paste content with fake card names (e.g., "1 Nonexistent Card XYZ\n1 Lightning Bolt"). Click "Parse & Resolve". Verify "Failed Cards" group appears with red header, failed rows have red-tinted background with error messages. Summary bar shows failed count in red. Resolved cards still appear in their own group.
- **Testability**: Full -- use obviously fake card names to guarantee failures.
- **Why now**: Mixed success/failure display is a critical UX path. Users will encounter this regularly.

### csv_import_cancel_after_resolve
- **Description**: After resolving, click "Cancel". Verify results panel shows "Cancelled. Paste new data to start over." and resolved/parsed data is cleared.
- **Testability**: Full -- standard cancel flow.
- **Why now**: Cancel is a basic interaction contract.

### csv_import_assign_to_deck
- **Description**: After resolving cards, verify the assign target dropdown has optgroups for Decks (Bolt Tribal, Eldrazi Ramp) and Binders (Trade Binder, Foil Collection). Select a deck, click "Add to Collection", verify success.
- **Testability**: Full -- fixture has decks and binders.
- **Why now**: Assignment is a key workflow option. Dropdown population must be verified.
- **Note**: Absorbs `csv_import_assign_to_binder` -- the dropdown mechanics are identical for both deck and binder optgroups. Verifying the optgroup structure covers both.

### csv_import_batch_metadata_in_commit
- **Description**: Fill in batch name (e.g., "Test Batch"), select product type "Booster Box", enter set code "FDN". Parse and resolve valid cards, then commit. Verify the commit succeeds. Verify batch name field is included when non-empty and excluded when empty.
- **Testability**: Full -- batch metadata is sent with the commit request.
- **Why now**: Batch metadata is a feature already partially covered by `csv_import_with_batch_metadata` (which checks field presence). This intent verifies the metadata is actually used in the commit flow.

---

## Deferred

### csv_import_format_dropdown_options
- **Reason**: Merged into `csv_import_page_structure`.

### csv_import_home_link_navigation
- **Reason**: Merged into `csv_import_page_structure`.

### csv_import_product_type_options
- **Reason**: Merged into `csv_import_page_structure`.

### csv_import_assign_to_binder
- **Reason**: Merged into `csv_import_assign_to_deck`. Dropdown mechanics are identical.

### csv_import_moxfield_format
- **Reason**: Requires Moxfield-specific CSV fixture data with correct column headers. The parse/resolve flow is identical to the deck list flow from the UI perspective. The format auto-detection is a server concern. Defer until Moxfield CSV fixtures exist.

### csv_import_file_upload_click
- **Reason**: File upload via Playwright can work, but requires a CSV fixture file. The drop zone interaction path (click -> hidden file input -> read -> populate textarea) adds complexity. Defer until fixture files are available.

### csv_import_parse_progress_messages
- **Reason**: Progress messages ("Parsing CSV...", "Parsed N rows. Resolving cards...") are transient. The parse+resolve cycle completes too quickly for intermediate states to be reliably captured in screenshots. Timing-dependent.

### csv_import_parse_api_error
- **Reason**: Requires crafting input that triggers a server-side parse error. Depends on server validation specifics that may change.

### csv_import_network_error
- **Reason**: Requires simulating network failures. Not practical in standard test harness.

### csv_import_commit_button_reenables_on_error
- **Reason**: Requires triggering a commit error with well-formed resolved data. Difficult without API manipulation.

### csv_import_drag_and_drop_visual_feedback
- **Reason**: Drag-and-drop simulation is unreliable in Playwright. Transient CSS changes are hard to screenshot.

### csv_import_mobile_layout
- **Reason**: Viewport manipulation for visual validation. Low priority.

### csv_import_resolved_card_thumbnails
- **Reason**: Covered by `csv_import_parse_and_resolve_decklist` which already verifies the resolved card table layout. Separate thumbnail verification is redundant.

### csv_import_all_failed_state
- **Reason**: Edge case of `csv_import_failed_cards_display`. The mixed-state test (some pass, some fail) is more representative of real usage. Pure all-fail is a rare scenario.
