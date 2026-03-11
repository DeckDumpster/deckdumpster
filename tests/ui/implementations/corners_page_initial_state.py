"""
Hand-written implementation for corners_page_initial_state.

Verifies the ingest corners page loads with correct initial state: camera
placeholder, drop zone, hidden results, empty messages, navigation links.
"""


def steps(harness):
    # Navigate to Ingest Corners page
    harness.navigate("/ingest-corners")

    # Verify camera placeholder and button
    harness.assert_visible("#camera-placeholder")
    harness.assert_visible("#camera-btn")

    # Verify drop zone with correct text
    harness.assert_visible("#drop-zone")
    harness.assert_text_present("Drop or select a photo of card corners")

    # Verify results section is hidden initially
    harness.assert_hidden("#results-section")

    # Verify header navigation links
    harness.assert_visible("header")
    harness.assert_text_present("Ingest Corners")
    harness.assert_visible("header a[href='/']")
    harness.assert_visible("header a[href='/upload']")
    harness.assert_visible("header a[href='/collection']")
    harness.assert_visible("header a[href='/batches']")

    # Verify New Session button is present
    harness.assert_text_present("New Session")

    harness.screenshot("final_state")
