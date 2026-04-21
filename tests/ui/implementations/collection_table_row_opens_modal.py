"""
Hand-written implementation for collection_table_row_opens_modal.

Clicks a card row in the virtually-scrolled table view and verifies
the card detail modal opens.
"""


def steps(harness):
    # Navigate to collection page
    harness.navigate("/collection")
    harness.wait_for_visible("#vtbody tr[data-idx]", timeout=5_000)

    # Click a card name to open the modal
    harness.click_by_selector("#vtbody tr[data-idx] .card-name")

    # Wait for modal to appear
    harness.wait_for_visible("#card-modal-overlay.active", timeout=5_000)
    harness.assert_visible("#card-modal")
    harness.screenshot("modal_open")

    # Close the modal
    harness.press_key("Escape")
    harness.wait_for_hidden("#card-modal-overlay.active")

    harness.screenshot("final_state")
