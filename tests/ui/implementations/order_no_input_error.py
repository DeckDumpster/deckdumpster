"""
Hand-written implementation for order_no_input_error.

Clicks Parse with empty textarea and verifies error message appears.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Click Parse with no input
    harness.click_by_selector("#parse-btn")

    # Verify error message
    harness.assert_text_present("No input provided.")

    harness.screenshot("final_state")
