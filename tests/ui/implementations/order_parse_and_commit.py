"""
Hand-written implementation for order_parse_and_commit.

End-to-end happy path: paste valid order text, parse, verify resolved results,
commit to collection, verify success message.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Paste valid order text (CK text format, auto-detected)
    harness.fill_by_selector(
        "#order-text",
        "1x Mountain [Foundations] - Near Mint\n1x Forest [Foundations] - Near Mint",
    )

    # Click Parse
    harness.click_by_selector("#parse-btn")

    # Wait for resolved results
    harness.wait_for_text("Resolved", timeout=500)
    harness.assert_visible(".order-group")

    # Commit to collection
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Added", timeout=500)

    harness.screenshot("final_state")
