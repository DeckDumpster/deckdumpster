"""
Hand-written implementation for collection_card_modal_detail.

Opens a card modal from the collection table and verifies card details
are displayed, then closes the modal.
"""


def steps(harness):
    # Navigate to Collection page (default is table view)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=5_000)
    harness.wait_for_visible(".collection-table tbody tr", timeout=5_000)

    # Click a card name cell to open the modal (avoid first cell which may have checkbox)
    harness.click_by_selector("tr[data-idx] td:nth-child(3)")

    # Wait for modal to appear
    harness.wait_for_visible("#card-modal-overlay.active", timeout=5_000)

    # Verify card modal is displayed
    harness.assert_visible("#card-modal")
    harness.screenshot("card_modal")

    # Close the modal
    harness.click_by_selector("#modal-close")

    # Verify modal is hidden
    harness.wait_for_hidden("#card-modal-overlay.active")

    harness.screenshot("final_state")
