"""
Hand-written implementation for sealed_partial_dispose_qty.

Verifies that disposing a subset of a multi-quantity entry splits it.
"""


def steps(harness):
    # Click on a product that has a qty>1 entry (Foundations)
    harness.click_by_text("Foundations", exact=False)
    harness.wait_for_visible("#detail-modal-overlay.active")

    # Set up dialog handler to respond with "2" when prompted
    harness.page.on("dialog", lambda dialog: dialog.accept("2"))

    # Click the Opened quick-dispose button (it has data-qty="6")
    harness.click_by_selector(".quick-dispose-btn.opened")

    # Modal should close and collection should reload
    harness.wait_for_hidden("#detail-modal-overlay.active")
    harness.page.wait_for_timeout(1000)

    # Verify the split happened — original should now show qty 4
    harness.assert_text_present("4")

    harness.screenshot("final_state")
