"""
Hand-written implementation for orders_list_pending_summary_and_badge.

Verifies the new /orders list page surfaces pending deliveries via the
header summary, the "N pending" badge on rows with ordered cards, and
the two button states (active "Receive All (N)" vs disabled "All
Received").
"""


def steps(harness):
    # start_page: /orders — auto-navigated by test runner.
    # Wait until at least one receive-btn has rendered so we know the
    # list has finished loading.
    harness.wait_for_visible("button.receive-btn")

    # Both sellers are visible on the page.
    harness.assert_text_present("CardHaus Gaming")
    harness.assert_text_present("Card Kingdom")

    # Header summary math: Card Kingdom has 5 ordered cards.
    harness.assert_text_present("5 cards awaiting delivery")

    # Pending badge on the Card Kingdom row.
    harness.assert_visible("span.count-pending")
    harness.assert_text_present("5 pending")

    # Card Kingdom row has the active Receive All (5) button, targeted
    # by its order id so we don't accidentally match the CardHaus row.
    harness.assert_visible("button.receive-btn[data-order-id='2']")
    harness.assert_text_present("Receive All (5)")

    # CardHaus row instead has the disabled "All Received" button.
    harness.assert_visible("button.receive-btn.received")
    harness.assert_text_present("All Received")

    harness.screenshot("final_state")
