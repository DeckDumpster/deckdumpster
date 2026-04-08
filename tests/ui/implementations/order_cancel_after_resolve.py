"""
Hand-written implementation for order_cancel_after_resolve.

Parses a valid order, then clicks Cancel and verifies the cancellation message.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Paste valid order text
    harness.fill_by_selector(
        "#order-text",
        "1x Mountain [Foundations] - Near Mint",
    )

    # Parse
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=500)

    # Cancel
    harness.click_by_selector("#cancel-btn")

    # Verify cancellation message
    harness.assert_text_present("Cancelled. Paste new data to start over.")

    harness.screenshot("final_state")
