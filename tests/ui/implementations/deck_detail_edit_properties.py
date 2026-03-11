"""
Hand-written implementation for deck_detail_edit_properties.

Opens the edit modal, changes name and format, saves, and verifies
the header updates.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for the deck to load
    harness.wait_for_text("Bolt Tribal")

    # Click Edit button
    harness.click_by_text("Edit")

    # Wait for the edit modal to appear
    harness.wait_for_visible("#deck-modal.active")

    # Clear and change the name
    harness.fill_by_selector("#f-name", "Bolt Tribal v2")

    # Change the format to Legacy
    harness.select_by_label("#f-format", "Legacy")

    # Click Save
    harness.click_by_selector("#btn-save-deck")

    # Wait for modal to close and header to update
    harness.wait_for_hidden("#deck-modal.active")
    harness.wait_for_text("Bolt Tribal v2")

    # Verify the updated name and format
    harness.assert_text_present("Bolt Tribal v2")
    harness.assert_text_present("legacy")

    harness.screenshot("final_state")
