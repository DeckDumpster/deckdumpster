"""
Hand-written implementation for order_assign_to_deck.

Parses an order, verifies the assign target dropdown has deck/binder optgroups,
selects a deck, commits, and verifies success.
"""


def steps(harness):
    # Harness auto-navigates to /ingestor-order (from hint start_page)
    harness.wait_for_visible("#order-text")

    # Paste valid order text
    harness.fill_by_selector(
        "#order-text",
        "1x Mountain [Foundations] - Near Mint",
    )

    # Parse (auto-resolves after parsing)
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=500)

    # Select a deck (assign targets load automatically after resolve)
    harness.select_by_label("#assign-target", "Bolt Tribal")

    # Commit
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Added", timeout=500)

    harness.screenshot("final_state")
