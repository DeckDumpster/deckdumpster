"""
Hand-written implementation for order_commit_ordered_guidance.

Commits an order with Ordered status and verifies the amber guidance message
with a link to /collection appears alongside the success message.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Verify Ordered is the default active status
    harness.assert_visible(".pill[data-value='ordered'].active")

    # Paste valid order text
    harness.fill_by_selector(
        "#order-text",
        "1x Mountain [Foundations] - Near Mint",
    )

    # Parse and wait for results
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=10000)

    # Commit
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Added", timeout=10000)

    # Verify guidance message about Ordered status
    harness.assert_text_present("Ordered")
    harness.assert_visible("a[href='/collection']")

    harness.screenshot("final_state")
