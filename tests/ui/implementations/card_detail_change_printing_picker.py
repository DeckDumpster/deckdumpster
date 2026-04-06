"""
Hand-written implementation for card_detail_change_printing_picker.

Opens the printing picker on the card detail page and verifies
it shows all available printings with correct badges, then
toggles it closed.
"""


def steps(harness):
    # start_page: /card/dsk/119 — Unstoppable Slasher (3 printings)
    harness.wait_for_text("Unstoppable Slasher")
    # Wait for copies section to load
    harness.wait_for_visible(".copy-section")
    # Click "Change" button to open the printing picker
    harness.click_by_text("Change")
    # Wait for the picker to load printings from the API
    harness.wait_for_visible(".printing-picker-list")
    # Verify all 3 printings appear
    harness.assert_element_count(".printing-option", 3)
    # Verify the current printing has the "Current" badge
    harness.assert_text_present("Current")
    # Verify owned count badge is present
    harness.assert_text_present("Owned:")
    harness.screenshot("picker_open")
    # Click "Change" again to toggle the picker closed
    harness.click_by_text("Change")
    harness.wait_for_hidden(".printing-picker-list")
    harness.screenshot("final_state")
