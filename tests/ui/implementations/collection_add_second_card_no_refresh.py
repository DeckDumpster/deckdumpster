"""
Test that the Add button works on consecutive modal opens without page refresh.

Opens a card modal, adds a card via the Add form, closes the modal,
opens a second card's modal, and successfully adds via the same Add flow.
Verifies the form appears on the second click (regression for event
listener accumulation bug).
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
    # Fill in purchase details for the first card.
    harness.fill_by_selector("#add-price", "1.00")
    harness.fill_by_selector("#add-source", "TestFirst")
    # Confirm the addition.
    harness.click_by_selector("#add-confirm-btn")
    harness.screenshot("first_card_added")
    # Close the modal.
    harness.click_by_selector("#modal-close")
    # Click the second card in grid view.
    harness.click_by_selector(".sheet-card[data-idx]:nth-child(2)")
    # Wait for the modal to reappear.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Click "Add" again — this is the regression check.
    harness.click_by_selector("#modal-add-btn")
    # The form must appear. Fill in details for the second card.
    harness.fill_by_selector("#add-price", "2.00")
    harness.fill_by_selector("#add-source", "TestSecond")
    # Confirm the second addition.
    harness.click_by_selector("#add-confirm-btn")
    harness.screenshot("second_card_added")
