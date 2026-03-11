# Ingest Corners Page UX Description

**URL:** `/ingest-corners`
**Source:** `mtg_collector/static/ingest_corners.html`
**Title:** Ingest Corners - MTG Collection

---

## 1. Page Purpose

The Ingest Corners page provides a streamlined workflow for adding Magic: The Gathering cards to a collection by photographing just the bottom-left corners of cards. Users can either use a live camera feed or upload/drop image files. The photo is sent to Claude Vision, which identifies cards from their corner information (set symbol, collector number, rarity). Detected cards are displayed in a review table where the user can adjust foil status and condition, optionally assign cards to a deck, and then commit them all to the collection in one action. This page is optimized for rapid bulk entry — the user can capture multiple photos in succession within a single session, each adding more cards.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "Ingest Corners" heading | Link (`<a>`) | `/ingest-corners` (self) | Header, leftmost |
| "Home" | Link (`<a>`) | `/` | Header |
| "Upload OCR" | Link (`<a>`) | `/upload` | Header |
| "Collection" | Link (`<a>`) | `/collection` | Header |
| "Batches" | Link (`<a>`) | `/batches` | Header |
| "New Session" | Button (`<button class="secondary">`) | N/A (JS action) | Header, right-aligned |

---

## 3. Interactive Elements

### Camera Section

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Open Camera button | `#camera-btn` | `<button>` | Shown in `#camera-placeholder`. On devices with camera API, opens the rear camera. On devices without `getUserMedia`, triggers a file input with `capture="environment"` (native camera app). |
| Camera video feed | `#camera-video` | `<video>` | Live video stream from the device camera. `autoplay playsinline`. Max height 55vh. |
| Camera canvas | `#camera-canvas` | `<canvas>` | Hidden canvas used to capture frames from the video feed. |
| Photo count badge | `#photo-count` | `<span>` | Overlay badge (top-right of camera view). Shows "N captured". Initially hidden; appears after first capture. Green text on semi-transparent black background. |
| Capture button | Inline `onclick="captureAndDetect()"` | `<button>` | Large button in camera controls. Captures current video frame as JPEG (92% quality), creates a timestamped file, and sends it for detection. |
| Close Camera button | Inline `onclick="stopCamera()"` | `<button class="secondary">` | Stops the camera stream, hides the camera view, and re-shows the Open Camera placeholder. |

### File Upload Section

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Drop zone | `#drop-zone` | `<div>` | Dashed-border area. Accepts drag-and-drop files or click to open file picker. Text: "Drop or select a photo of card corners". Gets `dragover` class on drag hover (border turns red). |
| File input | `#file-input` | `<input type="file">` | Hidden file input. Accepts `image/jpeg,image/png,image/webp`. Triggered by clicking the drop zone. |

### Processing Indicator

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Processing spinner | `#processing` | `<div>` | Hidden by default. Shows an animated spinner and text "Analyzing card corners with Claude Vision..." during API call. |

### Messages Area

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Messages container | `#messages` | `<div>` | Container for dynamically appended success, error, and skipped-cards messages. Each message auto-removes after 10 seconds. |

### Results Section

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Results section | `#results-section` | `<div>` | Hidden by default. Contains the detected cards table, deck selector, and action buttons. Shown after successful detection. |
| Results heading | N/A | `<h2>` | Text: "Detected Cards". |
| Results table | `.results-table` | `<table>` | Displays detected cards with columns: thumbnail image, Card Name, Set/CN, Rarity, Foil toggle, Condition dropdown, Remove button. |
| Results body | `#results-body` | `<tbody>` | Dynamically populated with one row per detected card. |
| Card thumbnail | `.thumb` (per row) | `<img>` | 40x56px card image from `image_uri`, or falls back to `/static/card_back.jpeg`. |
| Foil toggle | `.foil-toggle[data-idx="{idx}"]` | `<input type="checkbox">` | Per-card checkbox labeled "Foil". Pre-checked if the card was detected as foil. Changes update `currentCards[idx].foil`. |
| Condition select | `.condition-select[data-idx="{idx}"]` | `<select>` | Per-card dropdown with options: Near Mint (default), Lightly Played, Moderately Played, Heavily Played, Damaged. Pre-selected based on detection result. Changes update `currentCards[idx].condition`. |
| Remove button | `.remove-btn` (per row) | `<button>` | Red "x" button. Removes the card from `currentCards` and re-renders the table. If last card removed, hides the results section. |

### Deck Assignment Section

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Deck selector container | `#deck-selector` | `<div>` | Hidden by default. Shown when results are displayed. Contains deck dropdown, zone dropdown, and new deck form. |
| Deck dropdown | `#deck-select` | `<select>` | Options: "None" (default, value=""), "+ Create new deck..." (value="__new__"), plus dynamically loaded existing decks (value=deck ID, text=deck name with optional format). Selecting "None" means cards are added to collection without deck assignment. |
| Zone dropdown | `#zone-select` | `<select>` | Options: Mainboard (default), Sideboard, Commander. Only relevant when a deck is selected. |
| New deck form | `#new-deck-form` | `<div>` | Hidden by default. Shown when "+ Create new deck..." is selected in the deck dropdown. |
| New deck name | `#new-deck-name` | `<input type="text">` | Text input with placeholder "Deck name". Required for deck creation. |
| New deck format | `#new-deck-format` | `<select>` | Format dropdown with options: No format (default, value=""), Standard, Modern, Commander, Pioneer, Legacy, Vintage, Pauper. |
| Create deck button | Inline `onclick="createDeck()"` | `<button>` | Creates a new deck via API, reloads the deck list, and auto-selects the new deck. |
| Cancel new deck button | Inline `onclick="cancelNewDeck()"` | `<button class="secondary">` | Hides the new deck form and resets deck dropdown to "None". |

### Action Buttons

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Add to Collection button | `#commit-btn` | `<button>` | Primary action. Commits all current cards to the collection (and optionally to a deck). Text changes to "Adding..." while in flight. Disabled during API call. |
| Discard button | Inline `onclick="discardResults()"` | `<button class="danger">` | Red button. Clears current cards, hides results section and deck selector. No confirmation dialog. |
| Results count | `#results-count` | `<span>` | Shows "N card(s)" count next to the action buttons. |

### Session Management

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| New Session button | Inline `onclick="newSession()"` | `<button class="secondary">` | In header. Generates a new `batchUuid`, clears current cards, resets photo counter, hides results, clears messages, and shows a "New session started" success message. |

---

## 4. User Flows

### Flow 1: Camera Capture (Happy Path)
1. User navigates to `/ingest-corners`.
2. User clicks "Open Camera" button.
3. Browser prompts for camera permission. On grant, the rear-facing camera feed appears.
4. User positions cards so bottom-left corners are visible in the frame.
5. User clicks "Capture" button.
6. The current frame is captured as a JPEG, the photo counter badge appears ("1 captured").
7. The processing spinner shows "Analyzing card corners with Claude Vision...".
8. The results section hides (if previously shown from a prior capture).
9. Claude Vision processes the image and returns detected cards.
10. The results table appears with one row per detected card, showing name, set/CN, rarity, foil toggle, and condition selector.
11. The deck selector section appears below the table.
12. User reviews the detected cards, adjusting foil/condition as needed.
13. User optionally selects a deck and zone to assign the cards to.
14. User clicks "Add to Collection".
15. A success message appears: "Added N card(s) to collection: Card1, Card2, ..." (with deck name if assigned).
16. The results section and deck selector hide.
17. User can capture more photos without leaving the page (same session/batch).

### Flow 2: File Upload via Drop Zone
1. User clicks the drop zone area (or drags a file onto it).
2. File picker opens (or file is dropped — drop zone highlights with red border during drag).
3. User selects a JPEG, PNG, or WebP image of card corners.
4. Processing spinner appears.
5. Detection results appear in the table (same as Flow 1, step 10 onward).

### Flow 3: Camera Fallback (No getUserMedia)
1. On devices without `getUserMedia` (older mobile browsers), clicking "Open Camera" triggers a native file input with `capture="environment"`.
2. The native camera app opens.
3. User takes a photo and confirms.
4. The photo is sent for detection (same as Flow 2, step 4 onward).

### Flow 4: Assign to Existing Deck
1. After detection results appear, the deck selector shows.
2. User selects an existing deck from the dropdown.
3. User selects a zone (Mainboard, Sideboard, or Commander).
4. User clicks "Add to Collection".
5. Cards are added to the collection AND assigned to the selected deck/zone.
6. Success message mentions the deck name.

### Flow 5: Create New Deck During Ingest
1. User selects "+ Create new deck..." from the deck dropdown.
2. The new deck form appears with name input and format dropdown.
3. User enters a deck name and optionally selects a format.
4. User clicks "Create".
5. The deck is created via `POST /api/decks`, the dropdown refreshes, and the new deck is auto-selected.
6. The new deck form hides.
7. User proceeds to commit cards (assigned to the new deck).

### Flow 6: Cancel New Deck
1. User selects "+ Create new deck..." and the form appears.
2. User clicks "Cancel".
3. The form hides, deck dropdown resets to "None".

### Flow 7: Remove Individual Card from Results
1. Detection results show multiple cards.
2. User clicks the "x" button on a card they do not want to add.
3. The card is removed from `currentCards` and the table re-renders.
4. If the last card is removed, the results section hides entirely.

### Flow 8: Discard All Results
1. User clicks the red "Discard" button.
2. All current cards are cleared, results section and deck selector hide.
3. No confirmation dialog is shown.

### Flow 9: Start New Session
1. User clicks "New Session" in the header.
2. A new batch UUID is generated.
3. All state is cleared: current cards, image key, photo counter.
4. Results section hides, messages are cleared.
5. A "New session started" success message appears (auto-removes after 10 seconds).

### Flow 10: Multiple Captures in One Session
1. User captures a photo, reviews and commits the results.
2. User captures another photo (camera stays open).
3. New detection results replace any previous results.
4. The photo counter increments.
5. All commits within the session share the same `batchUuid`.

### Flow 11: Skipped Cards
1. Claude Vision detects corner markings but some cards lack a set code or collector number.
2. The API response includes a `skipped` array.
3. A red info banner appears: "N card(s) skipped (missing set code or collector number)".
4. Only the successfully resolved cards appear in the results table.
5. The skipped message auto-removes after 10 seconds.

---

## 5. Dynamic Behavior

### On Page Load
- **Deck list fetch:** `GET /api/decks` is called immediately. Response populates the deck dropdown with existing decks (each option shows name and optional format in parentheses).
- **Camera API check:** If `navigator.mediaDevices.getUserMedia` is not available, the "Open Camera" button is rewired to trigger a hidden file input with `capture="environment"` for native camera fallback.
- **Batch UUID generation:** A new `batchUuid` is generated via `crypto.randomUUID()` on page load.

### Camera Lifecycle
- **startCamera():** Requests rear camera (`facingMode: 'environment'`) at up to 1920x1080. Sets the video element's `srcObject`. Shows camera view, hides placeholder.
- **captureAndDetect():** Draws the current video frame onto a hidden canvas. Converts to JPEG blob at 92% quality. Creates a `File` object with a timestamped name (`corners_YYYY-MM-DDTHH-MM-SS_N.jpg`). Increments photo counter and shows the badge.
- **stopCamera():** Stops all video tracks, clears `srcObject`, hides camera view, re-shows placeholder, hides photo count badge.

### Detection Pipeline
- `detectFromFile(file)`:
  1. Shows `#processing`, hides `#results-section`, clears messages.
  2. Sends `POST /api/corners/detect` with `FormData` containing the file.
  3. On response:
     - Hides processing spinner.
     - If HTTP error: shows error message.
     - If `data.skipped` exists: shows skipped info banner.
     - If `data.errors` exists: shows each error as a separate error message.
     - If no cards detected: shows specific error "No cards detected in image. Make sure the bottom-left corners are visible."
     - On success: stores `currentCards` and `currentImageKey`, calls `renderResults()`.

### Results Rendering
- `renderResults()` builds table rows dynamically:
  - Each row: thumbnail (`image_uri` or card back fallback), card name, set code + collector number, rarity, foil checkbox, condition dropdown, remove button.
  - Foil checkbox and condition dropdown changes update the `currentCards` array in-place.
  - Shows results count ("N card(s)").
  - Shows the deck selector.

### Commit Flow
- `commitCards()`:
  1. Disables commit button, changes text to "Adding...".
  2. Builds payload: `{image_key, batch_uuid, cards: [{printing_id, foil, condition}], deck_id?, deck_zone?}`.
  3. `POST /api/corners/commit`.
  4. On success: shows success message with card names (and deck name if applicable), clears state, hides results/deck selector.
  5. On error: shows error message, re-enables button.
  6. Button always re-enables and resets text after the call completes.

### Deck Creation
- `createDeck()`:
  1. Reads name and optional format from the form.
  2. `POST /api/decks` with `{name, format}`.
  3. On success: reloads deck list, auto-selects the new deck, hides form, clears name input.
  4. On error: shows error message.

### Message System
- Three message types: `success-msg` (green), `error-msg` (red), `skipped-info` (red/dark red).
- All messages are appended to `#messages` div.
- Each message auto-removes after 10 seconds (`setTimeout`).
- `clearMessages()` empties the messages container (called before each new detection).

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `GET /api/decks` | GET | Page load | N/A | Array of `{id, name, format, ...}` |
| `POST /api/corners/detect` | POST | On capture/file upload | `FormData` with `file` field (JPEG/PNG/WebP) | `{cards: [{name, set_code, collector_number, rarity, foil, condition, printing_id, image_uri, ...}], skipped: [...], errors: [...], image_key: "corners_YYYYMMDD_HHMMSS.ext"}` |
| `POST /api/corners/commit` | POST | On "Add to Collection" click | `{image_key, batch_uuid, cards: [{printing_id, foil, condition}], deck_id?, deck_zone?}` | `{added: [{name, ...}]}` on success |
| `POST /api/decks` | POST | On "Create" deck click | `{name, format}` | `{id, name, format, ...}` |

### Required Data State
- **ANTHROPIC_API_KEY** must be set on the server. Without it, the detect endpoint returns HTTP 503 with "ANTHROPIC_API_KEY not set -- corner detection requires an API key".
- **Local card database** must be populated (`mtg cache all`) so that detected set codes and collector numbers can be resolved to printings.
- **Ingest images directory** must be writable for storing uploaded photos.
- **Decks** (optional) must exist in the database to appear in the deck dropdown. Can also be created inline.
- **Batches table** must exist for batch tracking. The batch is created on first commit if the UUID does not already exist.

---

## 7. Visual States

### State 1: Initial / Camera Closed
- **Condition:** Page just loaded, no camera active.
- **Appearance:** Camera placeholder shown with large "Open Camera" button. Drop zone visible below. Results section hidden. No messages.

### State 2: Camera Active
- **Condition:** User opened the camera.
- **Appearance:** Camera placeholder hidden. Camera view shown with live video feed, Capture button, and Close Camera button. Photo count badge hidden until first capture. Drop zone still visible below.

### State 3: Camera Active with Captures
- **Condition:** User has captured one or more photos.
- **Appearance:** Same as State 2, but photo count badge visible (top-right): "N captured" in green on dark background.

### State 4: Processing
- **Condition:** A photo has been submitted for detection, awaiting response.
- **Appearance:** Processing div visible with spinner animation and "Analyzing card corners with Claude Vision..." text. Results section hidden. Camera view remains as-is (if open).

### State 5: Results Displayed
- **Condition:** Detection returned one or more cards.
- **Appearance:** Processing hidden. Results section visible with table of detected cards. Deck selector visible. Action buttons (Add to Collection + Discard) visible with card count. Camera view remains open if it was active.

### State 6: Results with Deck Selected
- **Condition:** User selected a deck from the dropdown.
- **Appearance:** Same as State 5. Deck dropdown shows selected deck name. Zone dropdown (Mainboard/Sideboard/Commander) is visible and relevant.

### State 7: New Deck Form Open
- **Condition:** User selected "+ Create new deck..." from the dropdown.
- **Appearance:** Same as State 6. An additional sub-form appears below the deck row with name input, format dropdown, Create button, and Cancel button.

### State 8: Commit In Progress
- **Condition:** User clicked "Add to Collection", API call in flight.
- **Appearance:** Commit button disabled with text "Adding...". Discard button and table still visible.

### State 9: Commit Success
- **Condition:** Cards successfully added to collection.
- **Appearance:** Results section hidden. Deck selector hidden. Green success message appears: "Added N card(s) to collection: Card1, Card2, ..." (with optional "-- assigned to DeckName"). Message auto-removes after 10 seconds.

### State 10: Detection Error
- **Condition:** API returned an error or no cards detected.
- **Appearance:** Processing hidden. Red error message(s) appear in the messages area. Results section not shown. Examples: "No cards detected in image. Make sure the bottom-left corners are visible." or "Claude Vision error: ...".

### State 11: Partial Detection with Skipped Cards
- **Condition:** Some cards detected, some skipped due to missing set code or collector number.
- **Appearance:** Red/dark-red skipped info banner: "N card(s) skipped (missing set code or collector number)". Results table shows only the successfully resolved cards. Additional error messages may also appear.

### State 12: Drop Zone Drag Hover
- **Condition:** User is dragging a file over the drop zone.
- **Appearance:** Drop zone border changes from dashed blue (#0f3460) to dashed red (#e94560). Background gains a subtle red tint (5% opacity).

### State 13: Empty Results After Removal
- **Condition:** User removed all cards from the results table one by one.
- **Appearance:** Results section hidden. Page returns to State 1 or State 2 (depending on camera status).

### State 14: Network Error
- **Condition:** Fetch call failed (server down, network issue).
- **Appearance:** Red error message: "Network error: ..." in the messages area. Processing spinner hidden. Commit button re-enabled if it was a commit failure.

### State 15: New Session Started
- **Condition:** User clicked "New Session" in header.
- **Appearance:** Results section hidden. Messages cleared. Green success message: "New session started" (auto-removes after 10 seconds). Photo counter reset. Camera state unchanged.

### State 16: API Key Missing
- **Condition:** Server does not have `ANTHROPIC_API_KEY` configured.
- **Appearance:** After attempting detection, red error message: "ANTHROPIC_API_KEY not set -- corner detection requires an API key". No results shown.
