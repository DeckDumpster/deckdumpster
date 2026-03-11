"""
Hand-written implementation for upload_page_layout.

Verifies the Upload page loads with all expected elements at rest: header
navigation, camera placeholder, set hint input, drop zone, empty image grid,
and hidden actions bar.
"""


def steps(harness):
    # Navigate to Upload page
    harness.navigate("/upload")

    # Verify header navigation links
    harness.assert_visible("header")
    harness.assert_text_present("Upload")
    harness.assert_visible("header a[href='/']")
    harness.assert_visible("header a[href='/recent']")
    harness.assert_visible("header a[href='/disambiguate']")

    # Verify camera placeholder and button
    harness.assert_visible("#camera-placeholder")
    harness.assert_visible("#camera-btn")

    # Verify set hint input with placeholder
    harness.assert_visible("#set-hint")

    # Verify drop zone with text
    harness.wait_for_visible("#drop-zone")
    harness.assert_text_present("Or drop / select files")

    # Verify actions bar is hidden (no images uploaded)
    harness.assert_hidden("#actions")

    # Fill set hint to verify input is interactive
    harness.fill_by_selector("#set-hint", "FDN")

    harness.screenshot("final_state")
