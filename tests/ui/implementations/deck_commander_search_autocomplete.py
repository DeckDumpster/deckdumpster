"""
Hand-written implementation for deck_commander_search_autocomplete.

Opens the new deck modal, selects Commander format, and searches for
a legendary creature to verify autocomplete results appear.
"""


def steps(harness):
    # Navigate to decks page
    harness.navigate("/decks")
    harness.wait_for_text("New Deck", timeout=10000)

    # Open new deck modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Commander field should be hidden initially
    harness.assert_hidden("#commander-field")

    # Select Commander format
    harness.select_by_label("#f-format", "Commander / EDH")

    # Commander field should now be visible
    harness.assert_visible("#commander-field")

    # Type a search query
    harness.fill_by_selector("#f-commander", "judith")

    # Wait for autocomplete results
    harness.wait_for_visible("#commander-results.open", timeout=5000)

    # Verify results contain the expected card
    harness.assert_text_present("Judith, Carnage Connoisseur")

    harness.screenshot("commander_search_results")

    # Close modal
    harness.click_by_text("Cancel")

    harness.screenshot("final_state")
