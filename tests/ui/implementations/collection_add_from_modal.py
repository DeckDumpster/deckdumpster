"""
Hand-written implementation for collection_add_from_modal.

Opens a card modal, clicks Add, fills in purchase details, confirms.
"""


def steps(harness):
    # Wait for collection to load.
    harness.wait_for_visible("tr[data-idx]")
    # Switch to grid view for direct card click handler.
    harness.click_by_selector("#view-grid-btn")
    # Click the first card in grid view to open the modal.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal to appear.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Click the "Add" button to show the add form.
    harness.click_by_selector("#modal-add-btn")
    # Fill in purchase details.
    harness.fill_by_selector("#add-price", "5.00")
    harness.fill_by_selector("#add-source", "LGS")
    # Confirm the addition.
    harness.click_by_selector("#add-confirm-btn")
    harness.screenshot("final_state")
