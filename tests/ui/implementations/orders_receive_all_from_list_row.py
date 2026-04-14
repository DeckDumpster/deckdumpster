"""
Hand-written implementation for orders_receive_all_from_list_row.

End-to-end test of bulk-receive from the /orders list: click the
Receive All button on the Card Kingdom row, verify the backend flips
all 5 ordered cards to owned, and verify the UI re-renders without
the pending badge or summary.
"""


def steps(harness):
    # start_page: /orders — auto-navigated by test runner.
    harness.wait_for_visible("button.receive-btn[data-order-id='2']")

    # Starting state: Card Kingdom row has 5 pending.
    harness.assert_text_present("5 pending")
    harness.assert_text_present("5 cards awaiting delivery")

    # Click Receive All on the Card Kingdom row.
    harness.click_by_selector("button.receive-btn[data-order-id='2']")

    # Success toast confirms the bulk receive.
    harness.wait_for_text("Received 5 cards")

    # After the list reloads, the pending badge and summary are gone
    # and the row shows the disabled All Received state.
    harness.wait_for_hidden("span.count-pending")
    harness.assert_text_absent("5 pending")
    harness.assert_text_absent("5 cards awaiting delivery")
    harness.assert_text_present("All Received")

    harness.screenshot("final_state")
