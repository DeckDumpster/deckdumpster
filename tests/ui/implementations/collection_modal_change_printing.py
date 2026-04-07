"""
Hand-written implementation for collection_modal_change_printing.

Opens a card modal from the collection page, changes the printing
via the inline picker, and verifies the modal refreshes with one
fewer copy.
"""


def steps(harness):
    # start_page: /collection
    harness.wait_for_visible(".card-cell", timeout=500)
    # Search for Unstoppable Slasher
    harness.fill_by_placeholder("Search cards...", "Unstoppable")
    harness.press_key("Enter")
    # Wait for search results and click the card
    harness.wait_for_text("Unstoppable Slasher", timeout=500)
    harness.click_by_text("Unstoppable Slasher")
    # Wait for the card modal to open with copies loaded
    harness.wait_for_visible("#card-modal-overlay")
    harness.wait_for_visible(".copy-section", timeout=500)
    # Verify 2 copies are shown initially
    harness.assert_element_count(".copy-section", 2)
    harness.screenshot("modal_with_two_copies")
    # Click "Change" on the first copy to open the printing picker
    harness.click_by_selector(".copy-section .change-printing-btn")
    harness.wait_for_visible(".printing-picker-list")
    # Verify printings are listed with Current badge
    harness.assert_text_present("Current")
    harness.screenshot("picker_open_in_modal")
    # Click a different printing
    harness.click_by_selector(".printing-option:not(.current)")
    # After changing, the modal refreshes — only 1 copy remains
    harness.wait_for_text("Copies (1)", timeout=500)
    harness.assert_element_count(".copy-section", 1)
    harness.screenshot("final_state")
