"""
Hand-written implementation for decks_create_modal_validation.

Tries to save a deck without a name (alert auto-accepted), then enters
a name and saves successfully.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for page to load
    harness.wait_for_text("New Deck")

    # Open the modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Click Save without entering a name (alert auto-accepted)
    harness.click_by_text("Save")

    # Modal should still be open after the alert
    harness.assert_visible("#deck-modal.active")

    # Now fill in a name and save successfully
    harness.fill_by_selector("#f-name", "Validated Deck")
    harness.click_by_text("Save")

    # Wait for redirect to the new deck's unified page
    harness.wait_for_visible(".deck-header h2")
    harness.assert_text_present("Validated Deck")

    harness.screenshot("final_state")
