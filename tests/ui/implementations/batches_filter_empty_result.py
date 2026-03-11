"""
Hand-written implementation for batches_filter_empty_result.

Verifies that filtering to a type with no matching batches shows the
empty state message, and switching back to All restores the list.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    harness.wait_for_text("Wednesday evening scan")

    # Click the "OCR" filter pill (no OCR batches exist)
    harness.click_by_text("OCR")

    # Verify empty state message appears
    harness.wait_for_text("No batches yet")

    harness.screenshot("empty_filtered")

    # Click "All" to restore full list
    harness.click_by_text("All")

    # Verify batches reappear
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")

    harness.screenshot("final_state")
