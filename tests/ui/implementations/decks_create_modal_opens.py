"""
Hand-written implementation for decks_create_modal_opens.

Opens the New Deck modal and verifies all expected form fields are present,
including precon fields that appear when the checkbox is checked.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for page to load
    harness.wait_for_text("New Deck")

    # Click "New Deck" button
    harness.click_by_text("New Deck")

    # Wait for modal to appear
    harness.wait_for_visible("#deck-modal.active")

    # Verify modal title
    harness.assert_text_present("New Deck")

    # Verify core form fields are visible
    harness.assert_visible("#f-name")
    harness.assert_visible("#f-format")
    harness.assert_visible("#f-description")
    harness.assert_visible("#f-precon")
    harness.assert_visible("#f-sleeve")
    harness.assert_visible("#f-deckbox")
    harness.assert_visible("#f-location")

    # Verify Save and Cancel buttons
    harness.assert_text_present("Save")
    harness.assert_text_present("Cancel")

    # Verify precon fields are hidden
    harness.assert_hidden("#precon-fields")

    # Check the precon checkbox to reveal precon fields
    harness.click_by_selector("#f-precon")

    # Verify precon fields are now visible
    harness.assert_visible("#precon-fields")
    harness.assert_visible("#f-origin-set")
    harness.assert_visible("#f-origin-theme")
    harness.assert_visible("#f-origin-variation")

    harness.screenshot("final_state")
