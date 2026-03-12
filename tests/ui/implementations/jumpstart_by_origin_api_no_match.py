"""
Hand-written implementation for jumpstart_by_origin_api_no_match.

Verifies the Ingest Corners page has the Jumpstart detection UI
elements in place: the jumpstart-banner exists but is hidden by
default, alongside existing elements like the camera placeholder
and drop zone.
"""


def steps(harness):
    # start_page is /ingest-corners (auto-navigated by harness)

    # Verify the jumpstart banner element exists but is hidden
    harness.assert_hidden("#jumpstart-banner")

    # Verify camera placeholder is visible
    harness.assert_visible("#camera-placeholder")

    # Verify drop zone is visible
    harness.assert_visible("#drop-zone")
    harness.assert_text_present("Drop or select a photo of card corners")

    # Verify results section is hidden
    harness.assert_hidden("#results-section")

    # Verify New Session button
    harness.assert_text_present("New Session")

    harness.screenshot("final_state")
