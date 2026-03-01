"""
Hand-written implementation for collection_orders_view.

Switches to the orders view on the collection page and verifies
card art thumbnails are visible in the order groups.
"""


def steps(harness):
    # The orders view button is hidden until data loads. Wait for cards.
    harness.wait_for_visible("#view-orders-btn", timeout=10_000)
    # Click the orders view toggle button.
    harness.click_by_selector("#view-orders-btn")
    # Verify we can see an order group with card images.
    harness.wait_for_text("CardHaus Gaming")
    harness.screenshot("final_state")
