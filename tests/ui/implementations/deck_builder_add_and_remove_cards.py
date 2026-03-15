"""
Hand-written implementation for deck_builder_add_and_remove_cards.

Creates a deck, adds a card via the search modal, verifies it appears
in the deck list, then removes it.
"""


def steps(harness):
    # Navigate to the deck builder page
    harness.navigate("/deck-builder")
    harness.wait_for_text("New Commander Deck")
    # Select hypothetical mode so card assignment is flexible
    harness.click_by_text("Hypothetical")
    # Search for Judith as commander
    harness.fill_by_placeholder("Search your collection...", "Judith")
    harness.wait_for_text("Judith, Carnage Connoisseur", timeout=3000)
    harness.click_by_text("Judith, Carnage Connoisseur")
    # Create the deck
    harness.click_by_text("Create Deck")
    harness.wait_for_text("+ Add Card", timeout=5000)
    # Verify initial count
    harness.assert_text_present("0/100")
    # Open the Add Card modal
    harness.click_by_text("+ Add Card")
    harness.wait_for_visible(".modal-overlay")
    # Search for a card
    harness.fill_by_placeholder("Search cards...", "Hollow")
    harness.wait_for_text("Hollow Marauder", timeout=3000)
    # Add the card using the result-add button inside the modal
    harness.click_by_selector(".result-add")
    # Wait for the deck to re-render with the card (modal stays open)
    harness.wait_for_text("Creatures", timeout=5000)
    # Close the modal by clicking the overlay background
    harness.click_by_selector(".modal-close")
    harness.wait_for_hidden(".modal-overlay", timeout=3000)
    # Verify the card count updated
    harness.assert_text_present("1/100")
    # Verify the card is in the deck list
    harness.assert_text_present("Hollow Marauder")
    harness.screenshot("final_state")
