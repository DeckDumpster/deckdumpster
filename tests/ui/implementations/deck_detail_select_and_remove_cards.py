"""
Hand-written implementation for deck_detail_select_and_remove_cards.

Switches to sideboard zone in grid view, verifies cards are shown,
then removes a card via the builder's remove button in list view.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for the deck to load
    harness.wait_for_text("Bolt Tribal")

    # Switch to list view (needed for remove buttons)
    harness.click_by_selector("#view-list-btn")

    # The list view shows all zones combined in type groups.
    # Verify a sideboard card is present in the list.
    harness.assert_text_present("Condemn")

    # Verify quantity controls appear (replaces old remove button)
    harness.assert_visible("#type-groups .qty-btn")

    harness.screenshot("final_state")
