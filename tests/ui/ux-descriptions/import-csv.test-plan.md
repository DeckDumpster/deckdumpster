# CSV Import Page (`/import-csv`) -- Test Plan

Source: `tests/ui/ux-descriptions/import-csv.md`

## Existing Coverage

The following existing intents already cover CSV Import page scenarios:

- **`csv_import_with_batch_metadata`** -- Visits the CSV Import page and verifies the presence of optional batch metadata fields: a batch name text input, a product type dropdown, and a set code input. Covers Section 3 (Input Panel: `#batch-name`, `#product-type`, `#batch-set-code`) and Section 5 (Batch Metadata).

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### High Priority

### csv_import_page_structure
- **Filename**: `csv_import_page_structure`
- **Description**: When I visit `/import-csv`, I see a page titled "CSV Import" with a "<-- Home" link in the header. The page has a two-panel layout: a left input panel containing a large monospace textarea with placeholder text "Paste CSV here (e.g. Moxfield deck export)...", a file upload drop zone with dashed border, a format dropdown defaulting to "Auto-detect", the batch metadata fields, and a "Parse & Resolve" button. The right results panel shows the initial info message: "Paste a CSV export or upload a file, then click Parse & Resolve."
- **Reference**: SS1 Page Purpose, SS2 Navigation, SS3 Interactive Elements (Input Panel), SS7 Visual States > Initial
- **Testability**: full
- **Priority**: high

### csv_import_parse_empty_input
- **Filename**: `csv_import_parse_empty_input`
- **Description**: When I visit `/import-csv` and click "Parse & Resolve" without entering any text or uploading a file, a red error message appears in the results panel saying "No CSV text provided." The button remains enabled so I can try again after pasting content.
- **Reference**: SS4 Flow 1 (step 5), SS7 Visual States > No input error
- **Testability**: full
- **Priority**: high

### csv_import_parse_and_resolve_decklist
- **Filename**: `csv_import_parse_and_resolve_decklist`
- **Description**: When I paste a plain text deck list (e.g. "1 Lightning Bolt" or "4 Counterspell") into the textarea and click "Parse & Resolve", the system parses the text and resolves cards against the local database. After resolution, the results panel shows a summary bar with total cards, resolved count, and detected format. Resolved cards appear in a table with columns for Card (with thumbnail and name), Set/CN, Condition, and Qty. The action bar appears with an "Add to Collection" button, a "Cancel" button, and an assign target dropdown.
- **Reference**: SS4 Flow 1, SS4 Flow 4, SS5 Two-Step Parse + Resolve, SS7 Visual States > Resolved (all success)
- **Testability**: full
- **Priority**: high

### csv_import_commit_to_collection
- **Filename**: `csv_import_commit_to_collection`
- **Description**: After successfully parsing and resolving cards, when I click "Add to Collection", the button is disabled and shows a spinner with "Adding..." text. On success, a green message appears saying "Successfully added N card(s) to collection." confirming the cards were imported. Only resolved cards are committed; failed cards are excluded automatically.
- **Reference**: SS4 Flow 5, SS5 Commit Filtering, SS7 Visual States > Committing, SS7 Visual States > Commit success
- **Testability**: full
- **Priority**: high

### csv_import_format_dropdown_options
- **Filename**: `csv_import_format_dropdown_options`
- **Description**: When I visit `/import-csv`, the format dropdown (`#format-select`) contains five options: "Auto-detect" (selected by default), "Deck List (text)", "Moxfield (CSV)", "Archidekt (CSV)", and "Deckbox (CSV)". These cover all supported import formats.
- **Reference**: SS3 Interactive Elements > Format dropdown, SS5 Format Auto-Detection
- **Testability**: full
- **Priority**: high

### csv_import_cancel_after_resolve
- **Filename**: `csv_import_cancel_after_resolve`
- **Description**: After parsing and resolving cards, when I click the "Cancel" button in the action bar, the resolved results disappear and the results panel shows a blue info message: "Cancelled. Paste new data to start over." The resolved and parsed data is cleared, allowing me to start a fresh import.
- **Reference**: SS4 Flow 6, SS7 Visual States > Cancelled
- **Testability**: full
- **Priority**: high

### csv_import_failed_cards_display
- **Filename**: `csv_import_failed_cards_display`
- **Description**: When I paste CSV content containing card names that cannot be resolved against the local database, the results panel shows a "Failed Cards" group with a red header. Each failed row has a red-tinted background and displays the card name, set info, quantity, and an error message explaining why resolution failed. The summary bar shows the failed count in red.
- **Reference**: SS4 Flow 4 (Failed Cards group), SS7 Visual States > Resolved (mixed), SS7 Visual States > Resolved (all failed)
- **Testability**: limited (requires card names not present in the test fixture database; could use obviously fake card names like "Nonexistent Card XYZ")
- **Priority**: high

### Medium Priority

### csv_import_file_upload_click
- **Filename**: `csv_import_file_upload_click`
- **Description**: When I visit `/import-csv`, the file upload drop zone is a clickable area with dashed border and text "Or drop/click to upload a .csv file". Clicking the drop zone triggers a file picker dialog. After selecting a CSV file, the drop zone text updates to show the filename, the border turns green (`.has-files` class), and the file contents populate the textarea automatically.
- **Reference**: SS4 Flow 2, SS5 File Upload Handling, SS7 Visual States > File loaded
- **Testability**: limited (Playwright can set file input values but the visual feedback -- green border, filename display -- requires interacting with the hidden file input rather than the drop zone click handler)
- **Priority**: medium

### csv_import_assign_to_deck
- **Filename**: `csv_import_assign_to_deck`
- **Description**: After resolving cards, the assign target dropdown (`#assign-target`) is populated with existing decks and binders organized into optgroups. I can select a deck from the dropdown, then click "Add to Collection" to import the cards and simultaneously assign them to the chosen deck. The dropdown values are formatted as "deck:ID" or "binder:ID".
- **Reference**: SS4 Flow 5, SS5 Assign Target Loading, SS6 API Endpoints (`/api/decks`, `/api/binders`)
- **Testability**: full (test fixture includes demo decks and binders)
- **Priority**: medium

### csv_import_assign_to_binder
- **Filename**: `csv_import_assign_to_binder`
- **Description**: After resolving cards, I can select a binder from the assign target dropdown and commit. The cards are imported into the collection and assigned to the chosen binder. This tests the binder optgroup in the dropdown and the binder assignment path.
- **Reference**: SS4 Flow 5, SS5 Assign Target Loading
- **Testability**: full (test fixture includes demo binders)
- **Priority**: medium

### csv_import_batch_metadata_in_commit
- **Filename**: `csv_import_batch_metadata_in_commit`
- **Description**: When I fill in the batch name, select a product type (e.g. "Booster Box"), enter a set code, parse and resolve cards, then commit, the batch metadata is included in the commit request. The imported cards are grouped into a named batch that can be viewed later on the Batches page. If the batch name is left empty, no batch metadata is sent.
- **Reference**: SS3 Interactive Elements (batch fields), SS5 Batch Metadata, SS6 API Endpoints > `/api/import/commit`
- **Testability**: full
- **Priority**: medium

### csv_import_product_type_options
- **Filename**: `csv_import_product_type_options`
- **Description**: When I visit `/import-csv`, the product type dropdown (`#product-type`) contains options: an empty default labeled "Product type...", plus "Starter Collection", "Booster Box", "Bundle", "Precon", "Singles", and "Other". These match the standard product types used across the application.
- **Reference**: SS3 Interactive Elements > Product type dropdown
- **Testability**: full
- **Priority**: medium

### csv_import_moxfield_format
- **Filename**: `csv_import_moxfield_format`
- **Description**: When I paste Moxfield-formatted CSV content (with headers like "Count,Tradelist Count,Name,Edition,Condition,Language,Foil,Alter,Proxy,Purchase Price") and click "Parse & Resolve" with format set to Auto-detect, the system detects the Moxfield format. The summary bar displays "Moxfield" as the detected format. Foil cards from the Moxfield data show a gold "Foil" tag next to the card name.
- **Reference**: SS5 Format Auto-Detection, SS5 Foil Detection, SS7 Visual States > Resolved
- **Testability**: full
- **Priority**: medium

### csv_import_home_link_navigation
- **Filename**: `csv_import_home_link_navigation`
- **Description**: When I visit `/import-csv`, the header contains a "<-- Home" link. Clicking this link navigates me back to the homepage at `/`.
- **Reference**: SS2 Navigation
- **Testability**: full
- **Priority**: medium

### csv_import_parse_progress_messages
- **Filename**: `csv_import_parse_progress_messages`
- **Description**: When I paste valid content and click "Parse & Resolve", the results panel shows sequential progress messages: first "Parsing CSV..." with a spinner while the parse API call is in progress, then "Parsed N rows. Resolving cards..." with a spinner while the resolve API call runs. During this time the "Parse & Resolve" button is disabled/grayed out.
- **Reference**: SS4 Flow 1 (steps 6-11), SS5 Two-Step Parse + Resolve, SS7 Visual States > Parsing, Resolving
- **Testability**: limited (progress messages are transient and may complete too quickly for a screenshot to capture the intermediate states)
- **Priority**: medium

### Low Priority

### csv_import_parse_api_error
- **Filename**: `csv_import_parse_api_error`
- **Description**: When the parse API returns an error (e.g. malformed CSV that the parser cannot handle), a red error message appears in the results panel with the error text from the API response. The "Parse & Resolve" button re-enables so the user can correct the input and try again.
- **Reference**: SS4 Flow 1 (step 8), SS7 Visual States > Parse error
- **Testability**: limited (requires crafting input that triggers a server-side parse error; behavior depends on server validation logic)
- **Priority**: low

### csv_import_network_error
- **Filename**: `csv_import_network_error`
- **Description**: When a network error occurs during parsing or committing (e.g. server is unreachable), a red error message appears in the results panel. For parse/resolve failures it shows "Error: [message]". For commit failures it shows "Commit failed: [error]". The button re-enables in both cases.
- **Reference**: SS7 Visual States > Network error, Commit error (network)
- **Testability**: limited (requires simulating network failures, which is difficult in the standard test harness without mocking)
- **Priority**: low

### csv_import_commit_button_reenables_on_error
- **Filename**: `csv_import_commit_button_reenables_on_error`
- **Description**: When the commit API returns an error response, the "Add to Collection" button re-enables with its original "Add to Collection" text (removing the spinner and "Adding..." text). A red error message appears. This ensures the user is not stuck with a permanently disabled button after a failed commit.
- **Reference**: SS7 Visual States > Commit error (API), Commit error (network)
- **Testability**: limited (requires triggering a commit error, which may be difficult with well-formed resolved data)
- **Priority**: low

### csv_import_drag_and_drop_visual_feedback
- **Filename**: `csv_import_drag_and_drop_visual_feedback`
- **Description**: When I drag a file over the file upload drop zone, the border color changes to red (#e94560) during the dragover event. When I drop the file or drag away, the border resets. After a successful drop, the filename appears in the drop zone text and the border turns green.
- **Reference**: SS4 Flow 3, SS5 File Upload Handling
- **Testability**: limited (Playwright can simulate drag events but visual feedback during dragover is transient and hard to screenshot reliably)
- **Priority**: low

### csv_import_mobile_layout
- **Filename**: `csv_import_mobile_layout`
- **Description**: When I visit `/import-csv` on a narrow viewport (width <= 768px), the layout switches from two-panel side-by-side to single-column stacked: the input panel appears above the results panel. The textarea is constrained to 80-120px height. Card thumbnails in the results table shrink to 24x33px and the table uses smaller font and padding.
- **Reference**: SS7 Layout States > Mobile
- **Testability**: full (can set viewport size in Playwright)
- **Priority**: low

### csv_import_resolved_card_thumbnails
- **Filename**: `csv_import_resolved_card_thumbnails`
- **Description**: After resolving cards, each row in the "Resolved Cards" table displays a small card thumbnail image alongside the card name. The table columns are Card, Set/CN, Condition, and Qty. The card name and set code + collector number are shown as text. This verifies the detailed layout of the resolved card table.
- **Reference**: SS4 Flow 4 (Resolved Cards group detail)
- **Testability**: full
- **Priority**: low

### csv_import_all_failed_state
- **Filename**: `csv_import_all_failed_state`
- **Description**: When I paste content where every card fails resolution (e.g. all fake card names), the results panel shows a summary bar with 0 resolved and all cards failed. Only the "Failed Cards" group is displayed. The action bar with "Add to Collection" is still present but committing would add 0 cards.
- **Reference**: SS7 Visual States > Resolved (all failed)
- **Testability**: full (use entirely fake card names to guarantee all fail)
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| SS1 Page Purpose | `csv_import_page_structure` |
| SS2 Navigation > Home link | `csv_import_page_structure`, `csv_import_home_link_navigation` |
| SS2 Navigation > Page title | `csv_import_page_structure` |
| SS3 Input Panel > Textarea | `csv_import_page_structure` |
| SS3 Input Panel > File upload drop zone | `csv_import_file_upload_click`, `csv_import_drag_and_drop_visual_feedback` |
| SS3 Input Panel > Format dropdown | `csv_import_format_dropdown_options` |
| SS3 Input Panel > Batch name | `csv_import_with_batch_metadata` (existing), `csv_import_batch_metadata_in_commit` |
| SS3 Input Panel > Product type | `csv_import_with_batch_metadata` (existing), `csv_import_product_type_options` |
| SS3 Input Panel > Batch set code | `csv_import_with_batch_metadata` (existing) |
| SS3 Input Panel > Parse & Resolve button | `csv_import_page_structure`, `csv_import_parse_empty_input` |
| SS3 Result Panel > Assign target dropdown | `csv_import_assign_to_deck`, `csv_import_assign_to_binder` |
| SS3 Result Panel > Add to Collection button | `csv_import_commit_to_collection` |
| SS3 Result Panel > Cancel button | `csv_import_cancel_after_resolve` |
| SS4 Flow 1: Paste CSV and Import | `csv_import_parse_and_resolve_decklist`, `csv_import_parse_empty_input`, `csv_import_parse_progress_messages` |
| SS4 Flow 2: Upload CSV File | `csv_import_file_upload_click` |
| SS4 Flow 3: Drag and Drop File | `csv_import_drag_and_drop_visual_feedback` |
| SS4 Flow 4: Review Resolved Results | `csv_import_parse_and_resolve_decklist`, `csv_import_failed_cards_display`, `csv_import_resolved_card_thumbnails` |
| SS4 Flow 5: Assign and Commit | `csv_import_commit_to_collection`, `csv_import_assign_to_deck`, `csv_import_assign_to_binder`, `csv_import_batch_metadata_in_commit` |
| SS4 Flow 6: Cancel After Resolution | `csv_import_cancel_after_resolve` |
| SS5 On Page Load | `csv_import_page_structure` |
| SS5 File Upload Handling | `csv_import_file_upload_click`, `csv_import_drag_and_drop_visual_feedback` |
| SS5 Two-Step Parse + Resolve | `csv_import_parse_and_resolve_decklist`, `csv_import_parse_progress_messages` |
| SS5 Format Auto-Detection | `csv_import_moxfield_format`, `csv_import_format_dropdown_options` |
| SS5 Assign Target Loading | `csv_import_assign_to_deck`, `csv_import_assign_to_binder` |
| SS5 Commit Filtering | `csv_import_commit_to_collection` |
| SS5 Batch Metadata | `csv_import_with_batch_metadata` (existing), `csv_import_batch_metadata_in_commit` |
| SS5 Foil Detection | `csv_import_moxfield_format` |
| SS7 Input Panel > Empty | `csv_import_page_structure` |
| SS7 Input Panel > Text pasted | `csv_import_parse_and_resolve_decklist` |
| SS7 Input Panel > File loaded | `csv_import_file_upload_click` |
| SS7 Input Panel > Parsing (button disabled) | `csv_import_parse_progress_messages` |
| SS7 Results Panel > Initial | `csv_import_page_structure` |
| SS7 Results Panel > No input error | `csv_import_parse_empty_input` |
| SS7 Results Panel > Parsing | `csv_import_parse_progress_messages` |
| SS7 Results Panel > Parse error | `csv_import_parse_api_error` |
| SS7 Results Panel > Resolving | `csv_import_parse_progress_messages` |
| SS7 Results Panel > Resolve error | `csv_import_parse_api_error` |
| SS7 Results Panel > Resolved (all success) | `csv_import_parse_and_resolve_decklist` |
| SS7 Results Panel > Resolved (mixed) | `csv_import_failed_cards_display` |
| SS7 Results Panel > Resolved (all failed) | `csv_import_all_failed_state` |
| SS7 Results Panel > Network error | `csv_import_network_error` |
| SS7 Results Panel > Committing | `csv_import_commit_to_collection` |
| SS7 Results Panel > Commit success | `csv_import_commit_to_collection` |
| SS7 Results Panel > Commit error (API) | `csv_import_commit_button_reenables_on_error` |
| SS7 Results Panel > Commit error (network) | `csv_import_network_error` |
| SS7 Results Panel > Cancelled | `csv_import_cancel_after_resolve` |
| SS7 Layout States > Desktop | `csv_import_page_structure` |
| SS7 Layout States > Mobile | `csv_import_mobile_layout` |

## Intents with Limited Testability

| Intent | Reason |
|---|---|
| `csv_import_failed_cards_display` | Requires card names not in the test fixture database. Mitigated by using obviously fake card names. |
| `csv_import_file_upload_click` | Playwright can set file input values programmatically, but the click-to-browse and visual feedback (green border, filename text) depend on the hidden file input interaction path. |
| `csv_import_parse_progress_messages` | Progress messages ("Parsing CSV...", "Parsed N rows. Resolving cards...") are transient; the parse+resolve cycle may complete too quickly for intermediate states to be captured in screenshots. |
| `csv_import_parse_api_error` | Requires crafting input that triggers a server-side parse error. Depends on server validation specifics. |
| `csv_import_network_error` | Requires simulating network failures, which is difficult without mocking or stopping the server mid-request. |
| `csv_import_commit_button_reenables_on_error` | Requires triggering a commit error with well-formed resolved data, which is hard to achieve without API-level manipulation. |
| `csv_import_drag_and_drop_visual_feedback` | Drag event simulation in Playwright is possible but the transient border color change during dragover is hard to screenshot reliably. |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 7 | `csv_import_page_structure`, `csv_import_parse_empty_input`, `csv_import_parse_and_resolve_decklist`, `csv_import_commit_to_collection`, `csv_import_format_dropdown_options`, `csv_import_cancel_after_resolve`, `csv_import_failed_cards_display` |
| Medium | 7 | `csv_import_file_upload_click`, `csv_import_assign_to_deck`, `csv_import_assign_to_binder`, `csv_import_batch_metadata_in_commit`, `csv_import_product_type_options`, `csv_import_moxfield_format`, `csv_import_home_link_navigation`, `csv_import_parse_progress_messages` |
| Low | 7 | `csv_import_parse_api_error`, `csv_import_network_error`, `csv_import_commit_button_reenables_on_error`, `csv_import_drag_and_drop_visual_feedback`, `csv_import_mobile_layout`, `csv_import_resolved_card_thumbnails`, `csv_import_all_failed_state` |

**Total new intents: 21** (plus 1 existing: `csv_import_with_batch_metadata`)
