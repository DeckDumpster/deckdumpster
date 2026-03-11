# CSV Import Page UX Description

**URL:** `/import-csv`
**Source:** `mtg_collector/static/import_csv.html`
**Title:** CSV Import - MTG Collection

---

## 1. Page Purpose

The CSV Import page allows users to import cards into their collection from CSV exports or deck list text. It supports multiple formats from popular MTG deck-building platforms (Moxfield, Archidekt, Deckbox) as well as plain text deck lists. Users paste CSV content or upload a file, the system parses and auto-detects the format, resolves card names against the local Scryfall database, and presents resolved/failed cards for review before committing to the collection. Cards can be grouped into a named batch and optionally assigned to a deck or binder.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "<-- Home" | `<a href="/">` | Home page | Header, leftmost |
| "CSV Import" | `<h1>` | N/A (current page title) | Header |

---

## 3. Interactive Elements

### Input Panel (left side)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| CSV text textarea | `#csv-text` | `<textarea>` | Large text area for pasting CSV or deck list content. Placeholder: "Paste CSV here (e.g. Moxfield deck export)...". Monospace font. Resizable vertically. Fills available panel height. |
| File upload drop zone | `#file-drop` | `<div class="file-upload">` | Dashed-border clickable area. Text: "Or drop/click to upload a .csv file". Supports drag-and-drop and click-to-browse. Changes border to green and shows filename when file is loaded. |
| Hidden file input | `#file-input` | `<input type="file" accept=".csv">` | Hidden file input triggered by the drop zone. Accepts single `.csv` file only (no `multiple` attribute). |
| Format dropdown | `#format-select` | `<select>` | CSV format selection. Options: Auto-detect (default), Deck List (text), Moxfield (CSV), Archidekt (CSV), Deckbox (CSV). |
| Batch name input | `#batch-name` | `<input type="text">` | Optional batch name. Placeholder: "e.g. Foundations Starter Collection". Full width. |
| Product type dropdown | `#product-type` | `<select>` | Optional product type for batch. Options: (empty default "Product type..."), Starter Collection, Booster Box, Bundle, Precon, Singles, Other. |
| Batch set code input | `#batch-set-code` | `<input type="text">` | Optional set code for the batch. Placeholder: "Set". Width: 70px. |
| Parse & Resolve button | `#parse-btn` | `<button class="btn-primary">` | Initiates parsing and resolution. Text: "Parse & Resolve". Single button triggers both steps sequentially. |

### Result Panel (right side, dynamically rendered)

| Element | ID | Type | Description |
|---------|----|------|-------------|
| Assign target dropdown | `#assign-target` | `<select>` | Deck/binder assignment dropdown. First option: "No deck/binder assignment". Populated with optgroups for Decks and Binders after resolution. |
| Add to Collection button | `#commit-btn` | `<button class="btn-primary">` | Commits resolved cards to the collection. Shows spinner while processing. |
| Cancel button | `#cancel-btn` | `<button class="btn-secondary">` | Cancels the import, clears resolved/parsed data, shows info message. |

### Display Containers

| Element | ID | Description |
|---------|----|-------------|
| Results panel | `#results` | Right-side panel showing status messages, resolved/failed card groups, and action controls. |

---

## 4. User Flows

### Flow 1: Paste CSV and Import

1. User pastes CSV content (e.g., Moxfield deck export) into the `#csv-text` textarea.
2. User optionally selects a format from `#format-select` (Auto-detect is usually sufficient).
3. User optionally fills in batch name, product type, and batch set code.
4. User clicks "Parse & Resolve".
5. If textarea is empty, an error message appears: "No CSV text provided."
6. The results panel shows "Parsing CSV..." with a spinner. The button is disabled.
7. `POST /api/import/parse` is called with the text and format.
8. If the API returns an error, a red error message appears. The button re-enables.
9. On success, a progress message shows: "Parsed N rows. Resolving cards..."
10. `POST /api/import/resolve` is called with the detected format and parsed rows.
11. If the resolve API returns an error, a red error message appears. The button re-enables.
12. On success, the resolved results render showing card groups and summary.

### Flow 2: Upload CSV File and Import

1. User clicks the file drop zone or drags a `.csv` file onto it.
2. File picker opens (or file is dropped) -- accepts `.csv` files. Only single file.
3. The drop zone text updates to show the filename and border turns green.
4. File contents are read via `FileReader` and placed into the `#csv-text` textarea.
5. User proceeds with Parse & Resolve as in Flow 1.

### Flow 3: Drag and Drop File

1. User drags a file over the drop zone.
2. The drop zone border color changes to red (#e94560) on dragover.
3. User drops the file.
4. Border resets. Filename appears in the drop zone text. Green border indicates file loaded.
5. File contents populate the textarea.

### Flow 4: Review Resolved Results

1. After parsing and resolution, the results panel shows:
   - Summary bar: total cards, resolved count, failed count (red if any), detected format name.
   - Action bar: assign target dropdown, "Add to Collection" button, "Cancel" button.
   - "Resolved Cards" group (if any resolved): card-group with header showing count, and item table with columns: Card, Set/CN, Condition, Qty. Each row shows: card thumbnail, card name (with foil tag if applicable), set code + collector number, condition, and quantity.
   - "Failed Cards" group (if any failed, header in red): item table with columns: Card, Set/CN, Qty, Error. Each row has red-tinted background showing card name, set info, quantity, and error message.

### Flow 5: Assign to Deck/Binder and Commit

1. User optionally selects a deck or binder from `#assign-target`.
2. User clicks "Add to Collection".
3. The button is disabled and shows a spinner with "Adding...".
4. `POST /api/import/commit` is called with: `format`, `cards` (only resolved ones), optional `assign_target`, optional `batch_name`, `product_type`, `batch_set_code`.
5. On success: a green success message shows "Successfully added N card(s) to collection. M skipped. E error(s): ..."
6. On error from API response: a red error message shows. The button re-enables.
7. On network error: a red error message shows. The button re-enables.

### Flow 6: Cancel After Resolution

1. User clicks "Cancel" in the action bar.
2. `resolvedData` and `parsedData` are set to null.
3. The results panel shows: "Cancelled. Paste new data to start over."

---

## 5. Dynamic Behavior

### On Page Load
- No API calls on load. The page starts with an empty textarea and an info message: "Paste a CSV export or upload a file, then click Parse & Resolve."

### File Upload Handling
- Drop zone click opens the hidden `#file-input` via `fileInput.click()`.
- Drag-and-drop is supported with visual feedback (border color change on dragover/dragleave/drop).
- Only single file is accepted (no `multiple` attribute on the file input).
- File is read via `FileReader.readAsText()` and placed into the textarea.
- The drop zone text updates to show the filename.
- The drop zone gets `.has-files` class (green border).

### Two-Step Parse + Resolve
- Both steps happen sequentially within a single "Parse & Resolve" button click.
- Step 1: `POST /api/import/parse` -- extracts rows from CSV text, detects format.
- Step 2: `POST /api/import/resolve` -- matches parsed card data to the local database.
- Progressive status messages keep the user informed during each step.
- The detected format is stored in `detectedFormat` and displayed in the summary bar.

### Format Auto-Detection
- When "Auto-detect" is selected, the parse API determines the format (Moxfield, Archidekt, Deckbox, or plain text deck list).
- The detected format label is displayed in the summary bar after resolution.

### Assign Target Loading
- After resolution renders, `loadAssignTargets()` fetches `/api/decks` and `/api/binders` in parallel.
- Results populate the `#assign-target` dropdown with optgroups.
- Option values formatted as `deck:ID` or `binder:ID`.

### Commit Filtering
- Only resolved cards (`c.resolved === true`) are sent in the commit request.
- Failed cards are excluded automatically.

### Batch Metadata
- Batch name, product type, and batch set code are optional.
- They are only included in the commit request if the batch name is non-empty.
- Product type and batch set code are nested under the batch concept.

### Foil Detection
- Foil status is determined from the CSV data (e.g., Moxfield's `Foil` column).
- If `card.raw.Foil` exists and is non-empty, a gold "Foil" tag is shown.

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/import/parse` | POST | First step of "Parse & Resolve" | `{ text: string, format: string }` | `{ format: string, total_rows: int, rows: [...] }` or `{ error: string }` |
| `/api/import/resolve` | POST | Second step (automatic) | `{ format: string, rows: [...] }` | `{ summary: { total, resolved, failed }, resolved: [{ resolved: bool, name, set_code, collector_number, image_uri, quantity, raw, error }] }` or `{ error: string }` |
| `/api/import/commit` | POST | Clicking "Add to Collection" | `{ format: string, cards: [...], assign_target?: string, batch_name?: string, product_type?: string, batch_set_code?: string }` | `{ cards_added: int, cards_skipped: int, errors: string[] }` or `{ error: string }` |
| `/api/decks` | GET | After resolution renders | N/A | Array of deck objects with `id`, `name` |
| `/api/binders` | GET | After resolution renders | N/A | Array of binder objects with `id`, `name` |

### Data Prerequisites
- The local Scryfall card database must be populated for card resolution to work.
- CSV data must be in a recognized format (Moxfield, Archidekt, Deckbox CSV, or plain text deck list).
- Decks and/or binders must exist for the assignment feature to show options.

---

## 7. Visual States

### Input Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Empty** | No text or files | Empty textarea with placeholder. Drop zone shows "Or drop/click to upload a .csv file" with dashed border. |
| **Text pasted** | Textarea has content | Textarea shows the pasted CSV/deck list in monospace. |
| **File loaded** | File uploaded/dropped | Drop zone shows filename with green border. Textarea populated with file contents. |
| **Parsing** | Parse button clicked | Parse & Resolve button is disabled (grayed out). |

### Results Panel States

| State | Condition | Appearance |
|-------|-----------|------------|
| **Initial** | Page load | Blue info message: "Paste a CSV export or upload a file, then click Parse & Resolve." |
| **No input error** | Parse clicked with empty textarea | Red error message: "No CSV text provided." |
| **Parsing** | First API call in progress | Blue info with spinner: "Parsing CSV..." |
| **Parse error** | Parse API returns error | Red error message with error text. Button re-enables. |
| **Resolving** | Second API call in progress | Blue info with spinner: "Parsed N rows. Resolving cards..." |
| **Resolve error** | Resolve API returns error | Red error message with error text. Button re-enables. |
| **Resolved (all success)** | All cards resolved | Summary bar (total, resolved, format). Action bar. "Resolved Cards" group with card table showing thumbnails, names, set/CN, condition, quantity. |
| **Resolved (mixed)** | Some cards failed resolution | Same as above plus "Failed Cards" group (red header) with error table. Failed rows have red-tinted backgrounds. Summary bar shows failed count in red. |
| **Resolved (all failed)** | No cards resolved | Summary bar shows 0 resolved, all failed. Only "Failed Cards" group shown. Action bar still present (commit would add 0 cards). |
| **Network error** | Fetch throws | Red error message: "Error: [message]". |
| **Committing** | Commit button clicked | Button shows spinner and "Adding..." text. Button is disabled. |
| **Commit success** | Commit completed successfully | Green success message: "Successfully added N card(s) to collection. M skipped. E error(s): ..." |
| **Commit error (API)** | Commit API returns error in response | Red error message with API error text. Button re-enables with "Add to Collection" text. |
| **Commit error (network)** | Commit fetch throws | Red error message: "Commit failed: [error]". Button re-enables. |
| **Cancelled** | Cancel button clicked | Blue info message: "Cancelled. Paste new data to start over." |

### Layout States

| Breakpoint | Behavior |
|------------|----------|
| Desktop (> 768px) | Two-panel layout: 400px input panel on left, flexible results panel on right. Textarea fills available height. |
| Mobile (<= 768px) | Single-column layout: input panel stacks above results panel. Textarea constrained to 80-120px height. Item tables use smaller font and padding. Card thumbnails shrink to 24x33px. |
