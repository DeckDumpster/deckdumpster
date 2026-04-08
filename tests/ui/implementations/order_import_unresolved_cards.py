"""
Hand-written implementation for order_import_unresolved_cards.

Parses order text with cards that can't be found in the database,
verifying unresolved warnings appear in the results.
"""


def steps(harness):
    # Navigate to Order Ingestion page
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Paste order with a card that doesn't exist
    harness.fill_by_selector(
        "#order-text",
        "1x Nonexistent Card [Fake Set] - Near Mint",
    )

    # Click Parse
    harness.click_by_selector("#parse-btn")

    # Wait for results with failed resolution
    harness.wait_for_text("Failed", timeout=500)

    # Verify unresolved card styling appears
    harness.assert_visible(".unresolved")

    harness.screenshot("final_state")
