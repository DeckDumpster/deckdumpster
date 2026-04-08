"""
Hand-written implementation for order_import_parse_and_review.

Pastes order text, parses it, and verifies resolved results appear
with card entries in an order group.
"""


def steps(harness):
    # Navigate to Order Ingestion page
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Paste a CK-text format order (auto-detected)
    harness.fill_by_selector(
        "#order-text",
        "1x Mountain [Foundations] - Near Mint\n1x Forest [Foundations] - Near Mint",
    )

    # Click Parse
    harness.click_by_selector("#parse-btn")

    # Wait for resolved results to appear
    harness.wait_for_text("Resolved", timeout=500)

    # Verify order group appears with card entries
    harness.assert_visible(".order-group")

    harness.screenshot("final_state")
