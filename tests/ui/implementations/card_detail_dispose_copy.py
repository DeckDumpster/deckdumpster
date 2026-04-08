"""
Hand-written implementation for card_detail_dispose_copy.

Disposes of an owned copy by selecting "Sold" with price and note.
"""


def steps(harness):
    # start_page: /card/woe/171 — auto-navigated by test runner.
    harness.wait_for_text("Graceful Takedown")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=500)
    # Select "Sold" from the dispose dropdown.
    harness.select_by_label(".dispose-select", "Sold")
    # Fill in sale price and note.
    harness.fill_by_selector(".dispose-price", "5.00")
    harness.fill_by_selector(".dispose-note", "eBay sale")
    # Click the Dispose button.
    harness.click_by_selector(".dispose-btn")
    # After disposal, the copy should show a disposition badge.
    harness.wait_for_visible(".disposition-badge", timeout=500)
    harness.screenshot("final_state")
