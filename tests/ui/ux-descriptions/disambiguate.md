# Disambiguate Page UX Description

**URL:** `/disambiguate`
**Source:** `mtg_collector/static/disambiguate.html`
**Title:** Disambiguate - Card Ingest

---

## 1. Page Purpose

The Disambiguate page presents cards that have been identified by the OCR/Claude Vision ingest pipeline but could not be automatically resolved to a single printing. Each card is shown alongside its candidate printings (different sets, art variants, etc.) so the user can visually select the correct match and confirm it. This is a manual review step that bridges the gap between automated card recognition and final collection entry — the user picks the exact printing, chooses a finish (nonfoil/foil/etched), and confirms each card one at a time until the queue is empty.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "Disambiguate" heading | Link (`<a>`) | `/` (Home) | Header, leftmost |
| "Home" | Link (`<a>`) | `/` | Header |
| "Upload" | Link (`<a>`) | `/upload` | Header |
| "Recent" | Link (`<a>`) | `/recent` | Header |
| "Upload some photos" | Link (`<a>`) | `/upload` | Empty state message |
| "View Collection" | Link (`<a>`) | `/collection` | Shown in empty state after all cards are confirmed |

---

## 3. Interactive Elements

### Per-Card Block (dynamically generated, one per pending card)

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Card block container | `#card-block-{idx}` | `<div>` | Wrapper for each pending card. Has `data-image-id` and `data-card-idx` attributes. Gets class `resolved` when confirmed (triggers fade-out animation). |
| Crop thumbnail | `#crop-{idx}` | `<div class="crop-thumb">` | Displays a cropped view of the original uploaded photo, zoomed to the detected card region. Clickable — opens photo modal (zoom-in cursor). |
| Confirm button | `.confirm-btn[data-idx="{idx}"]` | `<button>` | Confirms the selected candidate for this card. Starts **disabled**; becomes enabled only after a candidate is selected. Text changes to "..." while the API call is in flight. |
| Finish selector | `.finish-select[data-idx="{idx}"]` | `<select>` | Dropdown with options: "Nonfoil" (default), "Foil", "Etched". Auto-set to "Foil" when a foil-only candidate is selected. |
| Search input | `.search-input[data-idx="{idx}"]` | `<input type="text">` | Pre-filled with the card name from Claude's OCR result. User can edit and search for different cards. Placeholder: "Search by card name...". Pressing Enter triggers search. |
| Search button | `.search-btn[data-idx="{idx}"]` | `<button class="secondary">` | Triggers a manual card name search. Text changes to "..." during the API call. |
| Candidate rows | `.candidate-row[data-printing-id="{id}"]` | `<div>` | Clickable card printing options displayed in a grid. Each shows a set icon (Keyrune font) and card image. Clicking selects the candidate (red border), deselects others, enables the Confirm button, and auto-sets the finish dropdown. Has a tooltip (`title`) showing card name, set name, and optional price. |
| "Show all N candidates" button | Dynamically created inline `<button>` | `<button>` | Appears when the narrowing algorithm reduces the visible candidates. Clicking replaces the narrowed list with the full unfiltered candidate list. |

### Global Elements

| Element | ID/Selector | Type | Description |
|---------|-------------|------|-------------|
| Status bar | `#status-bar` | `<span>` | Right-aligned in header. Shows "Confirmed: N" counter, updated after each confirmation. |
| Status summary | `#status-summary` | `<div>` | Below header. Shows "N card(s) pending disambiguation" or "N card(s) remaining" as cards are confirmed. Shows "All done! Confirmed N." when complete. |
| Empty state | `#empty-state` | `<div>` | Centered message shown when no cards need disambiguation. Contains heading and link to upload page. Repurposed as "All done!" state after all cards are confirmed. |
| Cards container | `#cards-container` | `<div>` | Holds all dynamically generated card blocks. |
| Dynamic settings style | `#dynamic-settings-style` | `<style>` | Injected CSS based on `/api/settings` response. Controls image display mode (`contain` vs `cover`) and icon background visibility. |

---

## 4. User Flows

### Flow 1: Standard Disambiguation (Happy Path)
1. User navigates to `/disambiguate`.
2. Page loads and fetches `/api/ingest2/pending-disambiguation`.
3. For each pending card, a card block renders with:
   - A cropped thumbnail of the original photo
   - Card metadata (name, mana cost, type, rules text, P/T, set/CN/artist)
   - The source image filename
   - A grid of candidate printings (narrowed by artist, set code, and collector number from Claude's metadata)
4. User reviews the original photo crop and metadata.
5. User clicks a candidate row in the grid to select it (red border appears, Confirm button enables).
6. The finish dropdown auto-sets based on the candidate's foil status.
7. User optionally adjusts the finish (nonfoil/foil/etched).
8. User clicks "Confirm".
9. The card block fades out and is removed from the DOM.
10. The status bar updates ("Confirmed: N"), and the remaining count updates.
11. After the last card is confirmed, the empty state shows "All done!" with a link to the collection.

### Flow 2: Manual Search Override
1. User is dissatisfied with the auto-narrowed candidates (wrong card or no good match).
2. User edits the text in the search input field (pre-filled with the detected card name).
3. User presses Enter or clicks "Search".
4. The search button shows "..." while the API call is in progress.
5. The candidates list replaces with results from `/api/ingest2/search-card`.
6. The Confirm button is disabled again (previous selection cleared).
7. User selects from the new candidate list and proceeds with confirmation.

### Flow 3: Expanding Narrowed Candidates
1. The narrowing algorithm filters candidates by artist, set code, and collector number.
2. If the narrowed list is smaller than the full candidate list, a "Show all N candidates" button appears below the grid.
3. User clicks "Show all N candidates".
4. The full unfiltered candidate list replaces the narrowed list.
5. User selects from the expanded list.

### Flow 4: Photo Zoom Modal
1. User clicks the cropped card thumbnail (zoom-in cursor).
2. A full-screen dark overlay (photo modal) appears showing the original photo at full resolution.
3. User clicks anywhere on the modal to dismiss it.

### Flow 5: Empty Queue
1. User navigates to `/disambiguate` with no pending cards.
2. The API returns an empty array.
3. The empty state is shown: "No cards to disambiguate" with a link to the upload page.

---

## 5. Dynamic Behavior

### On Page Load
- **Settings fetch:** `GET /api/settings` is called. Response controls CSS behavior for image display (`contain` vs `crop`) and set icon background visibility (`none` hides icons). Applied via injected `<style>` tag.
- **Pending cards fetch:** `GET /api/ingest2/pending-disambiguation` is called. Returns an array of objects, each containing `image_id`, `card_idx`, `image_filename`, `card_info` (Claude OCR result), `candidates` (Scryfall matches), and `crop` (bounding box coordinates).

### Candidate Narrowing (client-side)
- The `narrowCandidates()` function progressively filters candidates:
  1. Filter by artist name (case-insensitive substring match)
  2. Filter by set code (exact match)
  3. Filter by collector number (exact match)
- Each filter step only applies if it produces at least one match (otherwise skips).
- If narrowing reduces the count, a "Show all" button is appended.

### Candidate Grid Rendering
- All candidates render in **grid mode** (10 columns on desktop, 4 on mobile).
- Each candidate shows a Keyrune set icon (with rarity-based styling) and a card image (from `image_uri`).
- If no `image_uri`, a placeholder dark rectangle is shown.
- Set codes have fallback mappings (e.g., `tsb` -> `tsp`, `pspm` -> `spm`).

### Card Confirmation
- `POST /api/ingest2/confirm` with `{image_id, card_idx, printing_id, finish}`.
- On success (`data.ok`), the block gets class `resolved` (opacity 0, max-height 0 transition), then is removed after 350ms.
- After removal, remaining blocks are counted. If zero, the "All done!" state is shown.

### Search
- `POST /api/ingest2/search-card` with `{image_id, card_idx, query}`.
- Returns `{candidates: [...]}` which replaces the current candidate grid.
- The selected candidate reference is cleared; Confirm button re-disabled.

### Crop Thumbnail Rendering
- The original upload image is loaded from `/api/ingest/image/{filename}`.
- On `img.onload`, the crop bounding box (`x, y, w, h`) is used to calculate CSS `transform: translate() scale()` to zoom into the card region.
- If no crop data, the image is scaled to fit the container.

### Photo Modal
- Created dynamically as a `<div class="photo-modal">` appended to `<body>`.
- Fixed position, full viewport, dark background (rgba 0,0,0,0.9).
- Shows the source image at up to 95vw/95vh.
- Click anywhere to dismiss (removed from DOM).

---

## 6. Data Dependencies

### API Endpoints Called

| Endpoint | Method | When | Request Body | Response |
|----------|--------|------|-------------|----------|
| `/api/settings` | GET | Page load | N/A | `{image_display, icon_background, price_sources, ...}` |
| `/api/ingest2/pending-disambiguation` | GET | Page load | N/A | Array of `{image_id, card_idx, image_filename, card_info, candidates, crop}` |
| `/api/ingest/image/{filename}` | GET | Per card block | N/A | Image binary (JPEG/PNG) — the original uploaded photo |
| `/api/ingest2/confirm` | POST | On Confirm click | `{image_id, card_idx, printing_id, finish}` | `{ok: true}` on success |
| `/api/ingest2/search-card` | POST | On Search click/Enter | `{image_id, card_idx, query}` | `{candidates: [{printing_id, name, set_code, set_name, collector_number, rarity, artist, image_uri, price, foil, finishes, ...}]}` |

### Required Data State
- **Images must exist in `ingest_images` table** with `status = 'READY_FOR_DISAMBIGUATION'`. This status is set by the ingest pipeline after OCR/Claude processing identifies multiple candidate printings for a card.
- **`claude_result`** (JSON) must contain per-card metadata (name, type, mana_cost, set_code, collector_number, artist, etc.).
- **`scryfall_matches`** (JSON) must contain per-card arrays of candidate printings with `printing_id`, `name`, `set_code`, `set_name`, `collector_number`, `rarity`, `artist`, `image_uri`, `price`, `foil`, `finishes`.
- **`crops`** (JSON) should contain per-card bounding box objects `{x, y, w, h}` for thumbnail cropping.
- **`disambiguated`** (JSON) array tracks resolution status per card (`null` = unresolved).
- **Uploaded images** must be accessible at the ingest images directory path.
- **Local printings DB** must contain the printing referenced by `printing_id` (used for validation on confirm).

---

## 7. Visual States

### State 1: Empty Queue
- **Condition:** `/api/ingest2/pending-disambiguation` returns `[]`.
- **Appearance:** Centered empty state message: "No cards to disambiguate" with subtext linking to `/upload`. Status summary is blank. Cards container is empty.

### State 2: Cards Pending
- **Condition:** API returns one or more pending cards.
- **Appearance:** Status summary shows "N card(s) pending disambiguation". One card block per pending card, each containing a cropped photo, metadata, action buttons, search row, and candidate grid.

### State 3: Candidate Selected (per card)
- **Condition:** User has clicked a candidate row.
- **Appearance:** Selected candidate row has a red border (`border-color: #e94560`) and darker background. Confirm button is enabled (full opacity, clickable). Finish dropdown may have been auto-updated.

### State 4: No Candidate Selected (per card, initial state)
- **Condition:** Card block just rendered, or after a new search cleared the selection.
- **Appearance:** No candidate row highlighted. Confirm button is disabled (50% opacity, not clickable).

### State 5: Confirmation In Progress (per card)
- **Condition:** User clicked Confirm, API call in flight.
- **Appearance:** Confirm button disabled, text changed to "...".

### State 6: Card Resolved (per card, transient)
- **Condition:** API returned success for confirmation.
- **Appearance:** Card block fades out (opacity 0) and collapses (max-height 0, margin 0) over 300ms, then is removed from DOM.

### State 7: Search In Progress (per card)
- **Condition:** User triggered a search, API call in flight.
- **Appearance:** Search button disabled, text changed to "...".

### State 8: No Candidates Found (per card)
- **Condition:** Search returned empty results, or no candidates exist.
- **Appearance:** Centered gray text: "No candidates found" in the candidates list area.

### State 9: Narrowed vs Full Candidates (per card)
- **Condition:** `narrowCandidates()` reduced the visible list.
- **Appearance:** Grid shows only narrowed candidates, with a "Show all N candidates" button below. After clicking, the full grid is shown (button disappears).

### State 10: All Done
- **Condition:** Last card was confirmed, no remaining card blocks.
- **Appearance:** Empty state repurposed: heading changes to "All done!", subtext shows "Confirmed N card(s). View Collection" with link to `/collection`. Status summary shows "All done! Confirmed N." Status bar in header shows "Confirmed: N".

### State 11: Photo Modal Open
- **Condition:** User clicked a crop thumbnail.
- **Appearance:** Full-viewport dark overlay with the original photo displayed at full resolution. Cursor is `zoom-out`. Everything behind is obscured.

### State 12: Settings-Modified Display
- **Condition:** `/api/settings` returned `image_display: "contain"` or `icon_background: "none"`.
- **Appearance:** Card images use `object-fit: contain` instead of `cover` (shows full card art without cropping). Set icons may be transparent if icon_background is "none".
