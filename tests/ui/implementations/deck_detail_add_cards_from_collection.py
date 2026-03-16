"""
Hand-written implementation for deck_detail_add_cards_from_collection.

Opens the add-cards modal on deck 2, searches for "Cathar", selects
Cathar Commando, adds it, and verifies it appears in the deck grid.
"""


def steps(harness):
    # Navigate to deck 2 detail page
    harness.navigate("/decks/2")

    # Wait for the deck to load
    harness.wait_for_text("Eldrazi Ramp")

    # Click + Add Card button
    harness.click_by_selector("#add-card-btn")

    # Wait for the add-cards modal to appear
    harness.wait_for_visible("#add-cards-modal.active")

    # Search for "Cathar"
    harness.fill_by_placeholder("Search by name...", "Cathar")

    # Wait for search results
    harness.wait_for_text("Cathar Commando")

    # Click the result to select it
    harness.click_by_text("Cathar Commando")

    # Click Add Selected
    harness.click_by_text("Add Selected")

    # Wait for modal to close and deck to re-render with new card
    harness.wait_for_hidden("#add-cards-modal.active")

    # Verify the card appears in the grid (grid is default for small decks)
    harness.wait_for_visible(".grid-card-name")
    harness.assert_text_present("Cathar Commando")

    harness.screenshot("final_state")
