"""
Hand-written implementation for recent_batch_ingest.

Clicks Batch Ingest to remove DONE cards. DESTRUCTIVE -- must run after
other recent page tests.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")
    harness.wait_for_visible(".img-card.done")

    # Verify batch ingest button is visible
    harness.assert_visible("#batch-btn")

    # Click Batch Ingest
    harness.click_by_selector("#batch-btn")

    # Wait for DONE cards to be removed
    harness.wait_for_hidden(".img-card.done")

    # Verify success message appears with Collection link
    harness.wait_for_visible("#batch-msg")
    harness.assert_text_present("Collection")

    harness.screenshot("final_state")
