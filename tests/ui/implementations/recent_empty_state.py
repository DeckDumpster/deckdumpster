"""
Hand-written implementation for recent_empty_state.

Verifies the empty state elements exist in the DOM with correct content.
Since the fixture has images, #empty is hidden -- we verify it exists and
contains the expected heading and upload link.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")

    # Fixture has images, so summary should have content
    harness.assert_visible("#summary")

    # Batch button should be visible (fixture has DONE images)
    harness.assert_visible("#batch-btn")

    # The #empty div exists but is hidden (display:none) when images are present
    harness.assert_hidden("#empty")

    # Verify the empty state text is in the page source
    harness.assert_text_present("No recent images")
    harness.assert_text_present("Upload some photos")

    harness.screenshot("final_state")
