# Recent/Process Page UX Description

**URL:** `/recent`
**Source:** `mtg_collector/static/recent.html`
**Title:** "Recent Images - Card Ingest"

---

## 1. Page Purpose

The Recent page is the processing and review hub for uploaded card images. It displays all images in the ingest pipeline as a grid of cards, each showing its current processing status (processing, done, needs disambiguation, error). Users can click any image card to expand an inline accordion panel that shows detailed OCR/agent results, candidate card printings from Scryfall, and actions to confirm, correct, reprocess, search for alternative cards, or delete the image. Once images are resolved (status "done"), users can batch-ingest them into their collection with optional deck/binder assignment. The page supports two view modes (grid and table/list) with adjustable column counts.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "Recent Images" (title) | `<a>` in `<h1>` | `/` (Home) | Header, leftmost |
| "Home" | `<a>` | `/` | Header |
| "Upload" | `<a>` | `/upload` | Header |
| "Disambiguate" | `<a>` | `/disambiguate` | Header |
| "Upload some photos" | `<a>` | `/upload` | Empty state (centered, red text) |
| "Collection" link | `<a>` | `/collection` | Batch message (appears after successful batch ingest) |

---

## 3. Interactive Elements

### Header Controls

| ID / Selector | Type | Label / Content | Behavior |
|---------------|------|-----------------|----------|
| `#usage-box` | `<div>` | Token usage stats | Displays Claude API token usage and estimated cost (e.g., "~$0.0042" + "12K haiku"). Auto-refreshes every 30 seconds. |

### Column & View Controls (`.controls` bar)

| ID / Selector | Type | Label | Behavior |
|---------------|------|-------|----------|
| `#col-minus` | `<button>` | minus sign | Decreases grid column count by 1. Min: 1. Disabled at minimum. Repositions accordion if open. |
| `#col-count` | `<div>` | Current column number | Displays current column count. Not interactive. |
| `#col-plus` | `<button>` | "+" | Increases grid column count by 1. Max: 12. Disabled at maximum. Repositions accordion if open. |
| `#view-toggle` | `<button>` | hamburger icon / square icon | Toggles between grid view and table/list view. Persists choice to `localStorage` key `recent-view-mode`. In grid mode shows hamburger icon; in table mode shows square icon. |
| `#assign-target` | `<select>` | "No assignment" (default) | Dropdown populated on load with decks (optgroup "Decks") and binders (optgroup "Binders") from `/api/decks` and `/api/binders`. Selected value is sent with batch ingest or single-card ingest as `assign_target` (format: `deck:{id}` or `binder:{id}`). |
| `#batch-btn` | `<button>` | "Batch Ingest" | Sends all "done" images to the collection via `POST /api/ingest2/batch-ingest`. Hidden by default; shown only when at least one image has `done` status. Disabled during request. |
| `#batch-msg` | `<span>` | (dynamic) | Shows result message after batch ingest: "{N} photo(s) inserted: See them in Collection." with a link to `/collection`. |

### Grid Cards (`.img-card`)

| Selector | Type | Behavior |
|----------|------|----------|
| `.img-card` | `<div>` (clickable) | Each card represents an uploaded image. Clicking opens/closes the accordion detail panel below the card's row. Has `data-id` attribute with the image ID. CSS class reflects status: `.processing`, `.done`, `.needs_disambiguation`, `.error`. |
| `.finish-badge` | `<span>` (clickable) | Finish option badges (e.g., "foil", "nonfoil") overlaid on done cards with multiple finish options. Clicking a badge sends a confirm/correct API call to change the finish and refreshes the card. Has `data-img-id`, `data-scryfall-id`, `data-finish` attributes. Active badge has `.active` class with green border. |
| `.error-tooltip` | `<div>` | Visible on hover for error-status cards. Shows first 200 characters of the error message. |

### Accordion Panel (`#accordion-panel`)

The accordion is a single shared `<div>` that is repositioned in the DOM after the last card in the clicked card's row.

| Selector / ID | Type | Behavior |
|---------------|------|----------|
| `.acc-sidebar .card-title` | `<div>` | Displays the detected card name (or "No cards detected"). |
| Reprocess button | `<button>` | Label: "Reprocess" (with refresh icon). Confirms via `window.confirm()`, then calls `POST /api/ingest2/reset` to reset the image and reprocess from scratch. Removes any collection entries from this image. |
| Trace toggle button | `<button>` | Bug icon. Toggles visibility of the agent trace panel (OCR fragments, Claude agent trace, tool calls). |
| Delete button | `<button>` | "Delete". Class `.danger`. Confirms via `window.confirm()`, then calls `POST /api/ingest2/delete`. Removes image and any associated collection entries. |
| "Add to Collection" button | `<button>` | Primary button. Only visible for done cards (not pending, not `already_ingested`). Calls `POST /api/ingest2/batch-ingest` with `{ image_id: N }` and optional `assign_target`. On success, removes the card from the grid. |
| `#acc-search-input-{imgId}` | `<input type="text">` | Placeholder: "Replace with...". Pre-filled with detected card name. Pressing Enter triggers `accSearchCard()` to search for alternative cards via `POST /api/ingest2/search-card`. |
| `#acc-set-input-{imgId}` | `<input type="text">` | Placeholder: "Set code or name...". Pre-filled with detected set code. Pressing Enter (along with the search input) triggers a set-filtered search. |
| `.acc-candidate` | `<div>` (clickable) | Each candidate card printing shown as a small tile with Scryfall image, set icon (Keyrune), collector number overlay, and finish overlay. Clicking selects the candidate and sends confirm (`POST /api/ingest2/confirm`) or correct (`POST /api/ingest2/correct`) depending on whether the image is pending or already resolved. Selected candidate has green border (`.selected`). |
| "Show all N candidates" button | `<button>` | Secondary button. Shown when candidates have been narrowed. Clicking re-renders the full candidate list. |
| `.agent-trace` | `<div>` | Collapsible agent trace panel. Shows OCR fragments with bounding boxes and confidence scores, Claude agent conversation trace (tool calls, results), and final output JSON. Color-coded lines: OCR (grey), agent (blue), tool calls (orange), results (grey), final (green). |

---

## 4. User Flows

### Flow 1: View Processing Status

1. User navigates to `/recent`.
2. Page loads and calls `GET /api/ingest2/recent` to fetch all images in the pipeline.
3. Images are rendered as a grid of cards with color-coded borders:
   - Grey border: processing (OCR/agent still running)
   - Green border: done (card identified and confirmed)
   - Red border: needs disambiguation or error
4. Summary text above the grid shows counts: "{N} image(s): {X} processing, {Y} done, {Z} need disambiguation, {W} error".
5. For processing images, the page polls `GET /api/ingest2/recent?id={id}` every 3 seconds per image until status changes.
6. A discovery poll (`GET /api/ingest2/recent`) runs every 20 seconds to detect new images uploaded from other tabs/devices.

### Flow 2: Inspect a Card (Accordion Detail)

1. User clicks an image card in the grid.
2. The card gets a white border with a downward-pointing triangle indicator.
3. The accordion panel slides open below the card's row, spanning all columns.
4. The panel shows "Loading..." briefly while fetching `GET /api/ingest2/images/{id}`.
5. Once loaded, the panel shows:
   - **Sidebar:** Card name, Reprocess button, Trace toggle + Delete button row, "Add to Collection" button (if done), search input, set code input.
   - **Main area:** Candidate card printings from Scryfall as clickable tiles with images, set icons, collector numbers, and finishes.
6. The currently confirmed candidate (if any) is highlighted with a green border.
7. Clicking the same card again closes the accordion.

### Flow 3: Correct a Card Identification

1. User opens the accordion for a done or pending card.
2. User clicks a different candidate tile in the main area.
3. The page calls `POST /api/ingest2/confirm` (for pending) or `POST /api/ingest2/correct` (for done) with the new `printing_id` and `finish`.
4. The accordion refreshes, and the grid card updates its overlays (set icon, finish badge, card title).

### Flow 4: Search for an Alternative Card

1. User opens the accordion for any card.
2. User modifies the text in the search input (e.g., types a different card name).
3. (Optional) User enters a set code or set name in the set code input.
4. User presses Enter.
5. `POST /api/ingest2/search-card` is called with `{ image_id, card_idx: 0, query, set_code? }`.
6. The candidate area is replaced with search results.
7. User clicks a result to confirm/correct the identification.

### Flow 5: Change Finish via Badge (Quick Action)

1. A done card with multiple finish options (e.g., foil and nonfoil) shows clickable finish badges overlaid on the card image.
2. User clicks a badge (e.g., "foil").
3. `POST /api/ingest2/correct` or `/api/ingest2/confirm` is called with the selected finish.
4. The card updates in the grid: the clicked badge gets a green `.active` border, and the foil shimmer overlay toggles accordingly.

### Flow 6: Batch Ingest All Done Cards

1. When at least one card has "done" status, the green "Batch Ingest" button appears in the controls bar.
2. (Optional) User selects a deck or binder from the `#assign-target` dropdown.
3. User clicks "Batch Ingest".
4. `POST /api/ingest2/batch-ingest` is called (with optional `assign_target`).
5. On success, all done cards are removed from the grid.
6. The accordion closes if it was open.
7. A success message appears: "{N} photo(s) inserted: See them in Collection." with a link.

### Flow 7: Ingest a Single Card

1. User opens the accordion for a done card.
2. User clicks "Add to Collection" in the sidebar.
3. `POST /api/ingest2/batch-ingest` is called with `{ image_id: N }` and optional `assign_target`.
4. On success, the card is removed from the grid and the accordion closes.

### Flow 8: Reprocess an Image

1. User opens the accordion for any card.
2. User clicks the "Reprocess" button.
3. A confirmation dialog appears: "Reset this image and reprocess from scratch? Any cards already added from this image will be removed."
4. If confirmed, `POST /api/ingest2/reset` is called.
5. The accordion closes, the grid reloads via `loadRecent()`.

### Flow 9: Delete an Image

1. User opens the accordion for any card.
2. User clicks the red "Delete" button.
3. A confirmation dialog appears: "Delete this image and any collection entries from it?"
4. If confirmed, `POST /api/ingest2/delete` is called.
5. The card is removed from the grid, the accordion closes.

### Flow 10: View Agent Trace

1. User opens the accordion for any card.
2. User clicks the bug icon button.
3. The agent trace panel toggles visible/hidden.
4. The trace shows: OCR fragments with coordinates and confidence, Claude agent conversation steps (tool calls in orange, agent reasoning in blue, results in grey), and the final JSON output in green.

### Flow 11: Toggle View Mode (Grid vs Table)

1. User clicks the view toggle button (hamburger/square icon) in the controls bar.
2. The grid switches between:
   - **Grid mode:** Card images with overlays (set icon, finish badge, card title), 6 columns default (2 on mobile).
   - **Table mode:** Compact list rows with card name, set/CN/finish metadata, and side-by-side user photo + Scryfall thumbnail, 3 columns default (1 on mobile).
3. View mode is persisted in `localStorage` (`recent-view-mode`).
4. In table mode, Scryfall thumbnails are lazy-loaded by fetching detail data for each card.

### Flow 12: Adjust Column Count

1. User clicks the minus or plus buttons in the column controls.
2. The CSS `--grid-cols` variable updates, changing the grid layout.
3. If the accordion is open, it repositions to stay in the correct row.
4. Column count is tracked separately for grid and table modes.

---

## 5. Dynamic Behavior

### On Page Load
- `loadRecent()`: Fetches `GET /api/ingest2/recent` and renders all images. Starts per-image polling for any images with `processing` status.
- `loadUsageStats()`: Fetches `GET /api/ingest2/usage-stats` and renders token usage + cost in the header.
- `loadAssignTargets()`: Fetches `GET /api/decks` and `GET /api/binders` and populates the `#assign-target` dropdown with optgroups.
- `applyViewMode()`: Applies persisted view mode from `localStorage`.
- `applyGridCols()`: Sets initial column counts (responsive defaults: 6 grid / 3 table on desktop, 2 grid / 1 table on mobile).

### Polling
- **Per-image polling:** For each image with `border_status === 'processing'`, an interval polls `GET /api/ingest2/recent?id={id}` every 3 seconds. When status changes from `processing`, the poll stops for that image and the card/accordion are updated.
- **Discovery polling:** `GET /api/ingest2/recent` is polled every 20 seconds to discover new images uploaded from other tabs/devices. New images are prepended to the grid.
- **Usage stats polling:** `GET /api/ingest2/usage-stats` is refreshed every 30 seconds.
- Polling is managed via `activePolls` Map (image ID to interval ID). `syncPolls()` starts/stops polls based on current image statuses.

### Accordion Mechanics
- A single shared `<div>` (`#accordion-panel`) is repositioned in the DOM after the last card in the selected card's row.
- When columns change or view mode toggles, `repositionAccordion()` moves the panel to the correct position.
- Detail data is cached in `detailCache` Map but invalidated on every accordion open and after mutations.
- Candidate narrowing: `narrowCandidates()` filters candidates by matching artist, set code, and collector number from Claude's result. A "Show all" button expands to the full list.
- Candidates are expanded by finish: each candidate with multiple finishes (e.g., foil + nonfoil) produces separate tiles via `_expandByFinish()`.

### Card Element Updates
- `updateCardEl()` updates an existing card's status class, error icon/tooltip, overlays (set, finish, title), foil class, and info-row metadata without recreating the element.
- `createCardEl()` builds a new card element with all overlays, info-row (for table mode), crop zoom, and click handler.

### Crop Zoom
- `applyCropToImg()` uses `objectViewBox` CSS (inset) to zoom into the detected card area of the photo, using crop coordinates from the server (`img.crop`).

### Foil Shimmer
- Cards with `finish === 'foil'` get a CSS-animated rainbow gradient overlay (`.foil-shimmer`) that creates a holographic shimmer effect with a sweeping highlight animation.

### Keyrune Set Icons
- Set codes are mapped to Keyrune icon font classes. A fallback map handles known code mismatches (`tsb` -> `tsp`, `pspm` -> `spm`, `cst` -> `csp`).

### Scryfall Thumbnails (Table Mode)
- When table mode is active, `loadScryfallThumbnails()` iterates over all cards, fetches detail data staggered by 50ms delays, and sets the Scryfall thumbnail `src` attribute from the matched candidate's `image_uri`.

---

## 6. Data Dependencies

### API Endpoints Called

| Method | Endpoint | When | Request Body | Response |
|--------|----------|------|--------------|----------|
| `GET` | `/api/ingest2/recent` | Page load, discovery poll, after mutations | - | JSON array of image objects with `id`, `filename`, `stored_name`, `status`, `border_status`, `error_message`, `total_cards`, `done_count`, `pending_count`, `cards[]` (each with `name`, `set_code`, `collector_number`, `finish`, `image_uri`, `finish_options`, `finish_printing_id`), `crop`, `created_at`, `updated_at` |
| `GET` | `/api/ingest2/recent?id={id}` | Per-image polling, after mutations | - | JSON array (single element) of image object |
| `GET` | `/api/ingest2/images/{id}` | Accordion open | - | Detailed image object with `ocr_result[]`, `claude_result[]`, `scryfall_matches[][]`, `disambiguated[]`, `agent_trace[]`, `card_names[]`, `confirmed_finishes[]` |
| `GET` | `/api/ingest2/usage-stats` | Page load, every 30s | - | `{ images_with_usage, usage: { haiku: {input,output,...}, sonnet: {...}, opus: {...} }, estimated_cost_usd }` |
| `GET` | `/api/decks` | Page load | - | JSON array of deck objects |
| `GET` | `/api/binders` | Page load | - | JSON array of binder objects |
| `GET` | `/api/ingest/image/{stored_name}` | Image display | - | Raw image data |
| `POST` | `/api/ingest2/confirm` | Confirm a pending card identification | `{ image_id, card_idx, printing_id, finish }` | (refreshes after) |
| `POST` | `/api/ingest2/correct` | Correct an already-resolved card | `{ image_id, card_idx, printing_id, finish }` | (refreshes after) |
| `POST` | `/api/ingest2/search-card` | Search for alternative cards | `{ image_id, card_idx, query, set_code? }` | `{ candidates: [...] }` |
| `POST` | `/api/ingest2/reset` | Reprocess image | `{ image_id }` | (reloads page data) |
| `POST` | `/api/ingest2/delete` | Delete image | `{ image_id }` | (removes from grid) |
| `POST` | `/api/ingest2/batch-ingest` | Batch or single ingest | `{ assign_target?, image_id? }` | `{ ok: bool, count: number }` |
| `POST` | `/api/ingest2/remove-card` | Remove a card slot | `{ image_id, card_idx }` | (refreshes after) |

### Data Requirements
- Images must exist in the ingest pipeline (uploaded via `/upload` or API).
- For full functionality, the Anthropic API key must be configured (OCR/agent processing).
- Scryfall card data must be cached locally in the database for candidate matching.
- Decks and binders must exist in the database to appear in the assignment dropdown.

### External Resources
- Keyrune CSS (`cdn.jsdelivr.net/npm/keyrune@latest/css/keyrune.min.css`) for MTG set icons.
- Scryfall image CDN (`cards.scryfall.io`) for candidate card images and table-mode thumbnails.

---

## 7. Visual States

### Empty State
- Grid is empty/hidden.
- `#empty` div is shown: centered "No recent images" heading with "Upload some photos" link (red text, links to `/upload`).
- Batch Ingest button is hidden.
- Summary text is empty.

### Processing State (per card)
- Card has grey border (`.processing` class).
- No overlays (no set icon, no finish, no card title).
- Spinner icon is not shown on the card itself (just the grey border indicates processing).
- Per-image polling is active (every 3s).

### Done State (per card)
- Card has green border (`.done` class).
- Set icon overlay (bottom-left, Keyrune icon).
- Finish overlay or finish badges (bottom-right).
- Card title bar at bottom (white text, card name + collector number).
- If finish is "foil", the image has a rainbow shimmer animation overlay.
- Crop zoom applied via `objectViewBox` to focus on the card area.
- Hover: slightly lighter green border.

### Needs Disambiguation State (per card)
- Card has red border (`.needs_disambiguation` class).
- Partial overlays may be present depending on what was detected.
- Hover: lighter red border.

### Error State (per card)
- Card has red border (`.error` class).
- Large red "x" icon centered over the image.
- On hover: error tooltip appears at the bottom of the card with the error message (first 200 chars).

### Selected Card State
- Card has white border with white glow (`box-shadow`).
- Downward-pointing white triangle below the card (CSS `::after` pseudo-element).
- Card has `overflow: visible` and `z-index: 1` to show the triangle.

### Accordion Open State
- Full-width panel below the selected card's row.
- White border, dark blue background (`#1a2744`).
- Split layout: sidebar (left) + candidates (right, wrapping).

### Accordion "Already Ingested" State
- Sidebar shows card name, Reprocess, Trace, Delete buttons.
- Main area shows "Already ingested" text instead of candidates.
- No search inputs or "Add to Collection" button.

### Accordion "No Cards Detected" State
- Sidebar shows "No cards detected" title.
- Reprocess, Trace, Delete buttons available.
- Search inputs available for manual card lookup.
- Candidate area empty with "No candidates found. Try searching." message.

### Grid View Mode
- Cards displayed as image tiles with 4:5 aspect ratio.
- Overlays visible: set icon, finish badge/overlay, card title.
- Default columns: 6 (desktop), 2 (mobile).

### Table/List View Mode
- Grid class `.table-mode` applied.
- Card images hidden; replaced by info-row with:
  - Card name (bold, white) + metadata (set icon, set code, collector number, finish).
  - Side-by-side user photo and Scryfall thumbnail (each 50% width, height proportional to column width).
  - Foil shimmer applied to both images if applicable.
- Default columns: 3 (desktop), 1 (mobile).
- Grid-only overlays (set icon, finish badges, card title) hidden on cards.

### Batch Ingest Success State
- Done cards removed from grid.
- Accordion closed.
- Green success message in `#batch-msg`: "{N} photo(s) inserted: See them in Collection." with red link.
- Batch button re-enabled (may hide if no done cards remain).

### Usage Stats Display
- Top-right of header.
- Shows estimated cost in bold (e.g., "~$0.0042").
- Below: token breakdown by model tier (haiku, sonnet, opus) with abbreviated counts (K, M suffixes).
- Hidden if no tokens have been used.
