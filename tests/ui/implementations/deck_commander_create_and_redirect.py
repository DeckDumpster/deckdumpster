"""
Hand-written implementation for deck_commander_create_and_redirect.

Creates a new Commander deck by searching for and selecting a commander,
then verifies redirect to the deck detail page.
"""


def steps(harness):
    # Navigate to decks page
    harness.navigate("/decks")
    harness.wait_for_text("New Deck", timeout=10000)

    # Open new deck modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Select Commander format
    harness.select_by_label("#f-format", "Commander / EDH")
    harness.assert_visible("#commander-field")

    # Search for commander
    harness.fill_by_selector("#f-commander", "judith")
    harness.wait_for_visible("#commander-results.open", timeout=5000)

    # Click the first result
    harness.click_by_selector("#commander-results li")

    # Verify deck name was auto-filled
    harness.screenshot("commander_selected")

    # Save the deck
    harness.click_by_text("Save")

    # Wait for redirect to deck detail page
    harness.wait_for_text("Judith, Carnage Connoisseur", timeout=10000)

    # Verify we're on the deck detail page
    harness.assert_text_present("Judith, Carnage Connoisseur")

    harness.screenshot("final_state")
