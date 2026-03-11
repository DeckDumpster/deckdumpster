"""
Hand-written implementation for decks_create_minimal.

Creates a deck with only a name (no format, no description) and verifies
it redirects to the detail page.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for page to load
    harness.wait_for_text("New Deck")

    # Open the modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Fill in only the name
    harness.fill_by_selector("#f-name", "Minimal Deck")

    # Click Save (all other fields left at defaults)
    harness.click_by_text("Save")

    # Wait for redirect to the new deck's detail page
    harness.wait_for_visible("#deck-name")

    # Verify the deck name is shown
    harness.assert_text_present("Minimal Deck")

    # Verify empty card table message
    harness.assert_text_present("No cards in this zone")

    harness.screenshot("final_state")
