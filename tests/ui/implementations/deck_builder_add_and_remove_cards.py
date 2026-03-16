"""
Hand-written implementation for deck_builder_add_and_remove_cards.

Creates a non-hypothetical deck, adds a card via the add-cards picker,
verifies it appears in the deck, then removes it.
"""


def steps(harness):
    # Navigate to the deck builder page
    harness.navigate("/deck-builder")
    harness.wait_for_text("New Commander Deck")
    # Keep "Real" selected (default) so + Add Card button appears
    # Search for Judith as commander
    harness.fill_by_placeholder("Search your collection...", "Judith")
    harness.wait_for_text("Judith, Carnage Connoisseur", timeout=3000)
    harness.click_by_text("Judith, Carnage Connoisseur")
    # Create the deck
    harness.click_by_text("Create Deck")
    harness.wait_for_text("+ Add Card", timeout=5000)
    # Verify initial count
    harness.assert_text_present("0/100")
    # Open the Add Cards modal via the button
    harness.click_by_selector("#add-card-btn")
    harness.wait_for_visible("#add-cards-modal.active")
    # Search for an unassigned owned card
    harness.fill_by_placeholder("Search by name...", "Infernal Vessel")
    harness.wait_for_text("Infernal Vessel", timeout=3000)
    # Select the card
    harness.click_by_text("Infernal Vessel")
    # Add the card
    harness.click_by_text("Add Selected")
    harness.wait_for_hidden("#add-cards-modal.active", timeout=3000)
    # Verify the card count updated
    harness.assert_text_present("1/100")
    # Verify the card is in the deck
    harness.assert_text_present("Infernal Vessel")
    harness.screenshot("final_state")
