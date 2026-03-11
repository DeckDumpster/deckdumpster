"""
Hand-written implementation for order_no_orders_found.

Pastes garbage text that is not a recognized order format and verifies
the "No orders found" error appears.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Paste nonsense text
    harness.fill_by_selector(
        "#order-text",
        "this is random garbage text that is not an order format at all",
    )

    # Click Parse
    harness.click_by_selector("#parse-btn")

    # Wait for error
    harness.wait_for_text("No orders found in input.", timeout=10000)

    harness.screenshot("final_state")
