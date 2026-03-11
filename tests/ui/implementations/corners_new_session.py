"""
Hand-written implementation for corners_new_session.

Clicks the New Session button and verifies the success message appears.
"""


def steps(harness):
    # Navigate to Ingest Corners page
    harness.navigate("/ingest-corners")
    harness.assert_visible("#camera-placeholder")

    # Click the "New Session" button
    harness.click_by_text("New Session")

    # Verify success message appears
    harness.wait_for_visible(".success-msg")
    harness.assert_text_present("New session started")

    # Verify results section is still hidden
    harness.assert_hidden("#results-section")

    harness.screenshot("final_state")
