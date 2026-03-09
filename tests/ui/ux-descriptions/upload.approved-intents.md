# Upload Page — Approved Intents

## Implement Now

- `upload_page_layout` (existing, expand) — When I navigate to the Upload page, I see the header with navigation links (Home, Recent, Disambiguate) and the title "Upload" linking to the homepage. Below the header, I see the camera placeholder with an "Open Camera" button, an empty set hint input with placeholder "Set hint (e.g. FDN, Foundations)", the drop zone with "Or drop / select files" text, an empty image grid, and the actions bar is hidden. This is the only reliably testable visual state -- the page at rest with no images.

- `upload_file_upload_and_management` — I programmatically set files on the hidden `#file-input` to upload one or more images. After upload, each image appears as a thumbnail card in the image grid showing the filename and a red delete button. The actions bar becomes visible with "{N} image(s) uploaded" text and a "View Recent Images" button. When I click the delete button on an image card, the card is removed from the grid and the actions bar count decreases. If I delete all images, the actions bar disappears. Clicking "View Recent Images" navigates to `/recent`.

## Deferred

- `upload_existing_images_on_load` — When images already exist in READY_FOR_OCR state on the server, they appear in the grid on page load. Testable but requires pre-seeding the server with READY_FOR_OCR images via the upload API before navigating. Defer until the test fixture supports ingest pipeline state, or implement as a second-pass intent after the core two are stable.

- `upload_collision_error_message` — Uploading a file whose filename already exists on the server triggers a red error banner ("Already exists: {names} -- rename or delete first") that auto-dismisses after 8 seconds. Testable by uploading the same file twice via `setInputFiles`, but the 8-second auto-dismiss makes timing assertions fragile. Defer.

## Cut

- `upload_navigation_header` — Merged into `upload_page_layout`. Header navigation is visible on initial page load and does not need its own intent.

- `upload_initial_empty_state` — Merged into `upload_page_layout`. The empty state (hidden actions bar, empty grid, visible camera button, set hint, drop zone) is the initial page load state already covered by the expanded layout intent.

- `upload_file_via_drop_zone_click` — The click-to-open-picker interaction triggers a native OS file dialog that Playwright cannot control. The `setInputFiles` workaround bypasses the drop zone entirely. The upload result (grid population, actions bar) is covered by `upload_file_upload_and_management`.

- `upload_image_grid_display` — Merged into `upload_file_upload_and_management`. Grid display is verified as part of the upload-then-verify flow.

- `upload_actions_bar_appears` — Merged into `upload_file_upload_and_management`. Actions bar appearance is verified as part of the upload-then-verify flow.

- `upload_view_recent_images_navigation` — Merged into `upload_file_upload_and_management`. The "View Recent Images" click is the natural final step of the upload flow.

- `upload_delete_image` — Merged into `upload_file_upload_and_management`. Delete is verified as part of the upload-then-manage flow.

- `upload_multiple_files_at_once` — Functionally identical to `upload_file_upload_and_management` with multiple files passed to `setInputFiles`. No separate intent needed.

- `upload_set_hint_sent_with_upload` — The set hint value is sent as a form field but has no visible effect on the upload page UI. Verifying it was sent requires Playwright network interception, which goes beyond the standard intent/hint/implementation pattern. The UI shows no confirmation that the hint was used.

- `upload_delete_prevents_double_click` — Micro-interaction testing. Asserting `button.disabled === true` in the milliseconds between click and DOM removal is race-condition-prone and provides negligible regression value.

- `upload_drag_over_visual_feedback` — Requires dispatching synthetic drag events. Playwright's drag-and-drop simulation is unreliable, and the CSS class toggle (`.dragover`) is a trivial browser-side interaction. Low regression value.

- `upload_accepted_file_types` — Asserting the `accept` attribute on a hidden input element. This is a static HTML attribute, not application behavior. If it regresses, it means someone edited the HTML template and removed it, which would be caught in code review.

- `upload_no_polling_static_state` — Proving a negative (no network requests over time). Requires sustained network monitoring with arbitrary timeout. Untestable in any meaningful way.

- `upload_camera_open_and_close` — Requires `navigator.mediaDevices.getUserMedia`, a fake camera device via `--use-fake-device-for-media-stream`, and browser permission grants. This is environment-dependent and outside the scope of the Playwright harness, which uses basic click/fill interactions against a real server.

- `upload_camera_take_photo` — Same camera dependency as above. The fake camera produces a solid-color frame, so even if the camera could be simulated, the captured "photo" would be meaningless for visual verification.

- `upload_camera_fallback_no_getusermedia` — Requires overriding the `navigator.mediaDevices` browser API to simulate its absence. This is a device-level capability test, not an application behavior test.

- `upload_camera_permission_denied` — Requires Playwright to deny camera permissions and handle a browser `alert()` dialog. While technically possible, this tests browser permission UX, not application logic. The application's response is trivial (show the alert, stay on placeholder).
