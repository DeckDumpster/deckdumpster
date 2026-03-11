# Upload Page (`/upload`) -- Test Plan

Source: `tests/ui/ux-descriptions/upload.md`

## Existing Coverage

The following existing intent already covers an upload page scenario:

- **`upload_page_layout`** -- Verifies the page displays the drag-and-drop zone, set hint input field, and camera button on initial load.

All intents below are new and avoid duplicating that coverage.

---

## Proposed Intents

### upload_navigation_header
- **Description**: When I visit the Upload page, I can see header navigation links for "Home", "Recent", and "Disambiguate". The page title "Upload" in the header links back to the homepage. Clicking each link navigates to the correct destination.
- **References**: UX Description S2 Navigation (header links)
- **Testability**: full
- **Priority**: high

### upload_initial_empty_state
- **Description**: When I visit the Upload page with no pre-existing images in the READY_FOR_OCR state, I see the camera placeholder with the "Open Camera" button, an empty set hint input with the placeholder text "Set hint (e.g. FDN, Foundations)", the drop zone with "Or drop / select files" text, an empty image grid, and the actions bar is hidden.
- **References**: UX Description S7 Visual States > Initial State (No Images)
- **Testability**: full
- **Priority**: high

### upload_file_via_drop_zone_click
- **Description**: I can click the drop zone area to open the native file picker. After selecting one or more image files, the drop zone text changes to a spinner with "Uploading..." while the upload is in progress, then resets to "Or drop / select files" on completion. Each uploaded image appears as a thumbnail card in the image grid.
- **References**: UX Description S3 Interactive Elements > Drop Zone, S4 User Flows > Flow 1, S7 Visual States > Uploading State
- **Testability**: limited (requires programmatic file upload via Playwright's `setInputFiles` on the hidden `#file-input`; the click-to-open-picker flow itself is hard to automate, but setting files directly is reliable)
- **Priority**: high

### upload_set_hint_sent_with_upload
- **Description**: When I type a set hint (e.g. "FDN") into the set hint input field before uploading files, the hint value is included with the upload request. The set hint input retains its value across multiple uploads within the same session.
- **References**: UX Description S3 Interactive Elements > Inputs > #set-hint, S5 Dynamic Behavior > Upload Mechanics (set_hint read at upload time)
- **Testability**: limited (verifying the set_hint is sent requires intercepting the network request via Playwright route interception; the UI itself does not display the hint after upload)
- **Priority**: medium

### upload_image_grid_display
- **Description**: After uploading images, each image appears as a thumbnail card in the `#image-list` grid. Each card shows the image thumbnail, the filename below it, and a red "x" delete button in the top-right corner. Newly uploaded images are prepended to the grid (most recent first).
- **References**: UX Description S4 User Flows > Flow 1 (steps 7-8), S7 Visual States > Images Uploaded State, S5 Dynamic Behavior > Upload Mechanics (prepended)
- **Testability**: full (after programmatically uploading via `setInputFiles`)
- **Priority**: high

### upload_actions_bar_appears
- **Description**: After uploading one or more images, the actions bar becomes visible at the bottom of the page. It displays a count of "{N} image(s) uploaded" and a "View Recent Images" button. The count updates as more images are uploaded.
- **References**: UX Description S3 Interactive Elements > Buttons > "View Recent Images", S4 User Flows > Flow 1 (step 8), S7 Visual States > Images Uploaded State
- **Testability**: full (after programmatically uploading via `setInputFiles`)
- **Priority**: high

### upload_view_recent_images_navigation
- **Description**: After uploading images, I can click the "View Recent Images" button in the actions bar and the browser navigates to the `/recent` page.
- **References**: UX Description S2 Navigation > "View Recent Images", S4 User Flows > Flow 5
- **Testability**: full (after programmatically uploading via `setInputFiles`)
- **Priority**: high

### upload_delete_image
- **Description**: When I hover over an uploaded image card, the red "x" delete button is visible. Clicking it removes the card from the grid. The actions bar count updates accordingly. If all images are deleted, the actions bar is hidden.
- **References**: UX Description S3 Interactive Elements > Buttons > .delete-btn, S4 User Flows > Flow 4, S7 Visual States > Delete Button Disabled State
- **Testability**: full (after programmatically uploading via `setInputFiles`, then clicking delete)
- **Priority**: high

### upload_delete_prevents_double_click
- **Description**: When I click the delete button on an image card, the button is immediately disabled to prevent double-clicks. The card is removed from the DOM after the API call completes.
- **References**: UX Description S7 Visual States > Delete Button Disabled State
- **Testability**: full (can assert `button.disabled` is true immediately after click)
- **Priority**: medium

### upload_collision_error_message
- **Description**: When I upload a file with a filename that already exists on the server, a red error banner appears below the drop zone with text "Already exists: {filenames} -- rename or delete first". The error automatically disappears after approximately 8 seconds.
- **References**: UX Description S4 User Flows > Flow 1 (step 9), S5 Dynamic Behavior > Collision Handling, S7 Visual States > Collision Error State
- **Testability**: full (upload a file, then upload the same file again; wait for the error to appear and then auto-dismiss)
- **Priority**: high

### upload_drag_over_visual_feedback
- **Description**: When I drag a file over the drop zone, the border color changes to red and a faint red background tint appears (the `.dragover` CSS class is applied). When the file leaves the drop zone or is dropped, the styling reverts to normal.
- **References**: UX Description S3 Interactive Elements > Drop Zone (dragover behavior), S7 Visual States > Drag-Over State
- **Testability**: limited (Playwright can dispatch dragenter/dragleave events, but drag-and-drop simulation is unreliable across browsers; asserting CSS class changes is feasible but fragile)
- **Priority**: low

### upload_existing_images_load_on_page_open
- **Description**: When I visit the Upload page and there are already images in the READY_FOR_OCR state on the server, those images appear in the image grid on page load. The actions bar is visible with the correct count.
- **References**: UX Description S5 Dynamic Behavior > On Page Load (loadExisting), S6 Data Dependencies > GET /api/ingest2/images
- **Testability**: full (requires pre-seeding the server with READY_FOR_OCR images before navigating to the page; can be done via API calls in test setup)
- **Priority**: high

### upload_camera_open_and_close
- **Description**: When I click the "Open Camera" button and grant camera permission, the camera placeholder is hidden and a live video feed appears along with "Take Photo" and "Done" buttons. When I click "Done", the camera stream stops and the camera placeholder with "Open Camera" button reappears.
- **References**: UX Description S3 Interactive Elements > Buttons > #camera-btn, stopCamera() button, S4 User Flows > Flow 2 (steps 1-3, 9), S7 Visual States > Camera Active State
- **Testability**: limited (requires camera permission and a camera device; Playwright can grant permissions and use `--use-fake-device-for-media-stream` to simulate a camera, but this is environment-dependent)
- **Priority**: medium

### upload_camera_take_photo
- **Description**: When the camera is open, I click "Take Photo" to capture a frame. The photo count badge appears showing "1 taken" and increments with each subsequent photo. Each captured photo appears as a thumbnail in the image grid. The actions bar updates with the count.
- **References**: UX Description S3 Interactive Elements > Buttons > takePhoto(), S3 Camera Elements > #photo-count, S4 User Flows > Flow 2 (steps 4-8), S7 Visual States > Camera Active State (photo count badge)
- **Testability**: limited (same camera simulation requirements as upload_camera_open_and_close; additionally, the fake camera feed produces a solid color frame, so the thumbnail will be a blank image)
- **Priority**: medium

### upload_camera_fallback_no_getusermedia
- **Description**: On devices without getUserMedia support (e.g. HTTP on iOS), clicking "Open Camera" triggers a hidden file input with `capture="environment"`, opening the native camera app. The photo taken is handled the same as a file upload.
- **References**: UX Description S4 User Flows > Flow 3 (Camera Fallback), S5 Dynamic Behavior > Camera Lifecycle (fallback)
- **Testability**: limited (requires simulating absence of getUserMedia API; Playwright can override browser APIs but this is an unusual test setup and hard to validate end-to-end)
- **Priority**: low

### upload_camera_permission_denied
- **Description**: When I click "Open Camera" and deny camera permission, a browser alert displays "Camera error: {message}" and the page returns to the camera placeholder state with the "Open Camera" button visible.
- **References**: UX Description S7 Visual States > Camera Error State
- **Testability**: limited (Playwright can deny camera permissions via context options, and can handle the `dialog` event for the alert; feasible but requires specific permission configuration)
- **Priority**: medium

### upload_multiple_files_at_once
- **Description**: I can select multiple image files at once through the file picker. All files are uploaded in a single request, and all appear as thumbnail cards in the image grid. The actions bar shows the correct total count.
- **References**: UX Description S3 Interactive Elements > Inputs > #file-input (allows multiple), S5 Dynamic Behavior > Upload Mechanics
- **Testability**: full (Playwright's `setInputFiles` supports passing an array of files)
- **Priority**: medium

### upload_accepted_file_types
- **Description**: The file input only accepts JPEG, PNG, and WebP image files (as specified by the `accept` attribute on `#file-input`).
- **References**: UX Description S3 Interactive Elements > Inputs > #file-input (accepts image/jpeg,image/png,image/webp)
- **Testability**: full (can assert the `accept` attribute value on the input element)
- **Priority**: low

### upload_no_polling_static_state
- **Description**: After uploading images, the page does not poll for status changes or use SSE. The images remain displayed in READY_FOR_OCR state until I navigate away. The page is static after uploads complete.
- **References**: UX Description S5 Dynamic Behavior > No Polling or SSE
- **Testability**: limited (proving a negative -- no polling -- requires monitoring network requests over time; can be done with Playwright route interception but is inherently timing-dependent)
- **Priority**: low

---

## Coverage Matrix

| UX Description Section | Intent(s) |
|---|---|
| S1 Page Purpose | `upload_page_layout` (existing), `upload_initial_empty_state` |
| S2 Navigation > Header Links | `upload_navigation_header` |
| S2 Navigation > View Recent Images | `upload_view_recent_images_navigation` |
| S3 Interactive Elements > #camera-btn | `upload_camera_open_and_close` |
| S3 Interactive Elements > takePhoto() | `upload_camera_take_photo` |
| S3 Interactive Elements > stopCamera() / Done | `upload_camera_open_and_close` |
| S3 Interactive Elements > .delete-btn | `upload_delete_image`, `upload_delete_prevents_double_click` |
| S3 Interactive Elements > View Recent Images button | `upload_actions_bar_appears`, `upload_view_recent_images_navigation` |
| S3 Interactive Elements > #set-hint | `upload_initial_empty_state`, `upload_set_hint_sent_with_upload` |
| S3 Interactive Elements > #file-input | `upload_file_via_drop_zone_click`, `upload_multiple_files_at_once`, `upload_accepted_file_types` |
| S3 Interactive Elements > #drop-zone | `upload_file_via_drop_zone_click`, `upload_drag_over_visual_feedback` |
| S3 Camera Elements > #camera-video | `upload_camera_open_and_close` |
| S3 Camera Elements > #photo-count | `upload_camera_take_photo` |
| S4 User Flows > Flow 1 (File Upload) | `upload_file_via_drop_zone_click`, `upload_image_grid_display`, `upload_actions_bar_appears`, `upload_collision_error_message` |
| S4 User Flows > Flow 2 (Camera Capture) | `upload_camera_open_and_close`, `upload_camera_take_photo` |
| S4 User Flows > Flow 3 (Camera Fallback) | `upload_camera_fallback_no_getusermedia` |
| S4 User Flows > Flow 4 (Delete Image) | `upload_delete_image`, `upload_delete_prevents_double_click` |
| S4 User Flows > Flow 5 (Navigate to Recent) | `upload_view_recent_images_navigation` |
| S5 Dynamic Behavior > On Page Load | `upload_existing_images_load_on_page_open` |
| S5 Dynamic Behavior > Camera Lifecycle | `upload_camera_open_and_close`, `upload_camera_take_photo`, `upload_camera_fallback_no_getusermedia` |
| S5 Dynamic Behavior > Upload Mechanics | `upload_file_via_drop_zone_click`, `upload_set_hint_sent_with_upload`, `upload_multiple_files_at_once` |
| S5 Dynamic Behavior > Collision Handling | `upload_collision_error_message` |
| S5 Dynamic Behavior > No Polling or SSE | `upload_no_polling_static_state` |
| S6 Data Dependencies > GET images | `upload_existing_images_load_on_page_open` |
| S6 Data Dependencies > POST upload | `upload_file_via_drop_zone_click`, `upload_image_grid_display` |
| S6 Data Dependencies > POST delete | `upload_delete_image` |
| S6 Data Dependencies > GET image (display) | `upload_image_grid_display` |
| S7 Visual States > Initial State (No Images) | `upload_page_layout` (existing), `upload_initial_empty_state` |
| S7 Visual States > Camera Active State | `upload_camera_open_and_close`, `upload_camera_take_photo` |
| S7 Visual States > Images Uploaded State | `upload_image_grid_display`, `upload_actions_bar_appears` |
| S7 Visual States > Uploading State | `upload_file_via_drop_zone_click` |
| S7 Visual States > Collision Error State | `upload_collision_error_message` |
| S7 Visual States > Drag-Over State | `upload_drag_over_visual_feedback` |
| S7 Visual States > Camera Error State | `upload_camera_permission_denied` |
| S7 Visual States > Delete Button Disabled State | `upload_delete_prevents_double_click` |

## Priority Summary

| Priority | Count | Intents |
|---|---|---|
| High | 8 | `upload_navigation_header`, `upload_initial_empty_state`, `upload_file_via_drop_zone_click`, `upload_image_grid_display`, `upload_actions_bar_appears`, `upload_view_recent_images_navigation`, `upload_delete_image`, `upload_collision_error_message`, `upload_existing_images_load_on_page_open` |
| Medium | 6 | `upload_set_hint_sent_with_upload`, `upload_delete_prevents_double_click`, `upload_camera_open_and_close`, `upload_camera_take_photo`, `upload_camera_permission_denied`, `upload_multiple_files_at_once` |
| Low | 4 | `upload_drag_over_visual_feedback`, `upload_camera_fallback_no_getusermedia`, `upload_accepted_file_types`, `upload_no_polling_static_state` |

**Total new intents: 18** (plus 1 existing: `upload_page_layout`)

## Testability Summary

| Testability | Count | Intents |
|---|---|---|
| Full | 10 | `upload_navigation_header`, `upload_initial_empty_state`, `upload_image_grid_display`, `upload_actions_bar_appears`, `upload_view_recent_images_navigation`, `upload_delete_image`, `upload_delete_prevents_double_click`, `upload_existing_images_load_on_page_open`, `upload_multiple_files_at_once`, `upload_accepted_file_types` |
| Limited | 8 | `upload_file_via_drop_zone_click`, `upload_set_hint_sent_with_upload`, `upload_drag_over_visual_feedback`, `upload_camera_open_and_close`, `upload_camera_take_photo`, `upload_camera_fallback_no_getusermedia`, `upload_camera_permission_denied`, `upload_no_polling_static_state` |
