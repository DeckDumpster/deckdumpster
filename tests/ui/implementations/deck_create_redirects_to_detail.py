"""
Hand-written implementation for deck_create_redirects_to_detail.

Creates a new deck from the list page and verifies the browser redirects
to the new deck's standalone detail page.
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

    # Fill in deck name
    harness.fill_by_selector("#f-name", "Test Redirect Deck")

    # Select format
    harness.select_by_label("#f-format", "Pioneer")

    # Click Save
    harness.click_by_text("Save")

    # Wait for redirect to the new deck's detail page
    harness.wait_for_visible("#deck-name")

    # Verify we're on the standalone detail page with the new deck
    harness.assert_text_present("Test Redirect Deck")

    # Verify zone tabs are present (confirms standalone page, not list)
    harness.assert_text_present("Mainboard")

    # Verify empty card table message
    harness.assert_text_present("No cards in this zone")

    harness.screenshot("final_state")
