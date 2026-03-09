# Upload Page UX Description

**URL:** `/upload`
**Source:** `mtg_collector/static/upload.html`
**Title:** "Upload - Card Ingest"

---

## 1. Page Purpose

The Upload page is the entry point for ingesting Magic: The Gathering card images into the system. It provides two methods for capturing card images: a live camera interface (for mobile devices or webcams) and a file drop/select zone for uploading existing image files. Users can optionally specify a set hint to assist card identification. Uploaded images appear as thumbnail cards in a grid and are immediately sent to the server for storage and queuing (status `READY_FOR_OCR`). After uploading, users proceed to the Recent page to monitor processing and review results.

---

## 2. Navigation

| Element | Type | Target | Location |
|---------|------|--------|----------|
| "Upload" (title) | `<a>` in `<h1>` | `/` (Home) | Header, leftmost |
| "Home" | `<a>` | `/` | Header |
| "Recent" | `<a>` | `/recent` | Header |
| "Disambiguate" | `<a>` | `/disambiguate` | Header |
| "View Recent Images" | `<button>` inside `<a>` | `/recent` | Actions bar (bottom, visible only when images exist) |

---

## 3. Interactive Elements

### Buttons

| ID / Selector | Type | Label | CSS Class | Behavior |
|---------------|------|-------|-----------|----------|
| `#camera-btn` | `<button>` | "Open Camera" | (default primary) | Opens the device camera via `getUserMedia` or falls back to native file capture input on devices without `getUserMedia` |
| `takePhoto()` button | `<button>` (inline onclick) | "Take Photo" | (default primary, large) | Captures current video frame as JPEG, uploads immediately via `uploadBlob()` |
| `stopCamera()` button | `<button>` (inline onclick) | "Done" | `.secondary` | Stops camera stream, hides camera view, shows camera placeholder again |
| `.delete-btn` (per image card) | `<button>` (inline onclick) | "x" (times symbol) | `.delete-btn` | Deletes the image from the server via `POST /api/ingest2/delete` and removes the card from the grid |
| "View Recent Images" button | `<button>` inside `<a href="/recent">` | "View Recent Images" | (default primary) | Navigates to `/recent` |

### Inputs

| ID | Type | Placeholder | Behavior |
|----|------|-------------|----------|
| `#set-hint` | `<input type="text">` | "Set hint (e.g. FDN, Foundations)" | Free-text input for providing an MTG set code or name hint. Value is sent as `set_hint` parameter with each upload. Not required. |
| `#file-input` | `<input type="file">` | N/A (hidden) | Hidden file input; accepts `image/jpeg,image/png,image/webp`; allows `multiple` selection. Triggered by clicking the drop zone. |

### Drop Zone

| ID | Type | Behavior |
|----|------|----------|
| `#drop-zone` | `<div>` | Clickable area that opens the file picker (`#file-input`). Supports drag-and-drop: files dropped here are uploaded via `handleFiles()`. Visual feedback: adds `.dragover` class on dragover (dashed border turns red). During upload, inner text changes to a spinner + "Uploading...". |

### Camera Elements

| ID | Type | Behavior |
|----|------|----------|
| `#camera-video` | `<video>` | Live camera feed; `autoplay`, `playsinline` attributes. Requests rear camera (`facingMode: 'environment'`) at 1920x1080 ideal resolution. |
| `#camera-canvas` | `<canvas>` | Hidden canvas used to capture video frames for photo snapshots. |
| `#photo-count` | `<span>` | Badge overlay (top-right of camera view) showing "{N} taken" count for current camera session. Hidden by default, shown after first photo. |

---

## 4. User Flows

### Flow 1: Upload Files via Drop Zone / File Picker

1. User lands on the upload page.
2. (Optional) User types a set hint into the `#set-hint` input (e.g., "FDN").
3. User either:
   - Clicks the drop zone to open the native file picker, selects one or more images, or
   - Drags image files from their file manager and drops them onto the drop zone.
4. Drop zone text changes to spinner + "Uploading...".
5. Files are sent via `POST /api/ingest2/upload` as `FormData` with `files` field(s) and optional `set_hint`.
6. On success, drop zone text resets to "Or drop / select files".
7. Each uploaded image appears as a thumbnail card (prepended) in the `#image-list` grid.
8. The actions bar appears showing "{N} image(s) uploaded" and a "View Recent Images" button.
9. If any filenames collide with existing uploads, a red error banner appears below the drop zone: "Already exists: {names} -- rename or delete first". This auto-dismisses after 8 seconds.

### Flow 2: Capture Photos via Camera

1. User clicks "Open Camera" button.
2. Browser requests camera permission; if granted, the camera view appears (video feed + controls).
3. The camera placeholder is hidden; `#camera-view` is shown.
4. User taps "Take Photo" to capture the current frame.
5. The frame is drawn to a hidden canvas, converted to a JPEG blob (quality 0.92), and uploaded via `uploadBlob()` with an auto-generated filename (`camera_{timestamp}_{counter}.jpg`).
6. The `#photo-count` badge updates to show "{N} taken".
7. Each captured photo appears in the `#image-list` grid.
8. User can continue taking photos. Each is uploaded immediately.
9. When done, user taps "Done" to stop the camera stream and return to the placeholder state.

### Flow 3: Camera Fallback (No getUserMedia)

1. On devices without `getUserMedia` (e.g., HTTP on iOS), the "Open Camera" button triggers a hidden `<input type="file" capture="environment">`.
2. The native camera app opens; user takes a photo.
3. The photo is handled via `handleFiles()` (same as drop zone flow).

### Flow 4: Delete an Uploaded Image

1. User hovers over an image card in the `#image-list` grid.
2. A red "x" delete button is visible in the top-right corner.
3. User clicks the delete button.
4. `POST /api/ingest2/delete` is called with `{image_id: id}`.
5. The card is removed from the grid.
6. The actions bar count updates; if no images remain, the actions bar is hidden.

### Flow 5: Navigate to Recent/Process

1. After uploading images, user clicks "View Recent Images" button in the actions bar.
2. Browser navigates to `/recent` where uploaded images are being or have been processed.

---

## 5. Dynamic Behavior

### On Page Load
- `loadExisting()` is called: fetches `GET /api/ingest2/images?status=READY_FOR_OCR` to display any images already queued for processing.
- Existing images populate the `#image-list` grid.
- If images exist, the actions bar is shown with the count.

### Camera Lifecycle
- Camera stream is acquired via `navigator.mediaDevices.getUserMedia()`.
- Session-scoped counter (`sessionPhotos`) tracks photos taken in the current camera session (reset when camera is opened).
- Global counter (`photoCounter`) increments across the page lifetime for unique filenames.
- Camera fallback (hidden `<input capture="environment">`) is wired up at script initialization time if `getUserMedia` is unavailable.

### Upload Mechanics
- Files are uploaded as `multipart/form-data` to `POST /api/ingest2/upload`.
- The `set_hint` value is read from the input at upload time (not bound earlier).
- Upload response includes `uploaded` (array of image objects with `id`, `stored_name`, `filename`) and `collisions` (array of filenames that already exist).
- New image cards are prepended to the grid.

### Collision Handling
- If the server reports collisions (duplicate filenames), a styled error message div is dynamically inserted after the drop zone (or before `#image-list` for camera uploads).
- The error message auto-removes after 8 seconds via `setTimeout`.

### No Polling or SSE
- This page does not poll for status changes. Images remain in `READY_FOR_OCR` state until the user navigates to `/recent` where processing is triggered/monitored.

---

## 6. Data Dependencies

### API Endpoints Called

| Method | Endpoint | When | Request | Response |
|--------|----------|------|---------|----------|
| `GET` | `/api/ingest2/images?status=READY_FOR_OCR` | Page load | Query param `status` | JSON array of image objects (`id`, `filename`, `stored_name`) |
| `POST` | `/api/ingest2/upload` | File upload or camera capture | `multipart/form-data` with `files` (one or more) and optional `set_hint` | `{ uploaded: [...], collisions: [...] }` |
| `POST` | `/api/ingest2/delete` | Delete button clicked | `{ image_id: number }` | (response not checked) |
| `GET` | `/api/ingest/image/{stored_name}` | Image display | URL path param | Raw image data (JPEG/PNG/WebP) |

### Data Requirements
- The page functions with zero pre-existing data (empty grid, just the upload interface).
- No database card data, decks, binders, or collection entries are needed.
- Camera requires HTTPS (or localhost) and browser permission for `getUserMedia`.

---

## 7. Visual States

### Initial State (No Images)
- Camera placeholder visible: centered "Open Camera" button.
- Set hint input visible (empty).
- Drop zone visible: "Or drop / select files" text.
- Image grid (`#image-list`) is empty.
- Actions bar (`#actions`) is hidden (`display:none`).

### Camera Active State
- Camera placeholder hidden.
- Camera view visible: live video feed, "Take Photo" button, "Done" button.
- Photo count badge hidden initially, shown after first photo with green text "{N} taken".

### Images Uploaded State
- Image grid shows thumbnail cards in a responsive grid (min 100px columns).
- Each card shows: thumbnail image, filename below, red "x" delete button (top-right corner).
- Actions bar visible: "{N} image(s) uploaded" text + "View Recent Images" button.

### Uploading State
- Drop zone text replaced with spinner animation + "Uploading..." text.
- Returns to normal after upload completes.

### Collision Error State
- Red-background error message div inserted below the drop zone.
- Text: "Already exists: {filenames} -- rename or delete first".
- Auto-dismisses after 8 seconds.

### Drag-Over State
- Drop zone border color changes to red (`#e94560`).
- Faint red background tint appears.
- Reverts on drag leave or drop.

### Camera Error State
- If camera access is denied or fails, a browser `alert()` displays "Camera error: {message}".
- Falls back to camera placeholder state.

### Delete Button Disabled State
- When delete is clicked, the button is immediately disabled (`btn.disabled = true`) to prevent double-clicks.
- The card is removed from the DOM after the API call completes.
