"""
Hand-written implementation for edit_order_remove_card.

Removes a card from the order and verifies the summary bar updates.
Browser confirm() dialogs are auto-accepted.
"""


def steps(harness):
    # start_page: /orders/1 — auto-navigated by test runner.
    harness.wait_for_visible(".summary-bar")
    harness.wait_for_visible(".card-row")
    # Verify initial card count.
    harness.assert_text_present("5 cards")
    # Click the remove button on the first card row.
    harness.click_by_selector(".btn-icon.danger")
    # Confirm dialog is auto-accepted.
    # Wait for the card list to refresh.
    harness.wait_for_text("4 cards")
    harness.screenshot("final_state")
