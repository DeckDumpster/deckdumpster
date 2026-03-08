"""
Hand-written implementation for upload_page_layout.

Verifies the Upload page loads with all expected interactive elements.
"""


def steps(harness):
    # Navigate to Upload page
    harness.navigate("/upload")

    # Verify drag-and-drop zone is visible
    harness.wait_for_visible("#drop-zone")

    # Verify set hint input is visible
    harness.assert_visible("#set-hint")

    # Verify camera button is visible
    harness.assert_visible("#camera-btn")

    # Fill set hint to verify input is interactive
    harness.fill_by_selector("#set-hint", "FDN")

    harness.screenshot("final_state")
