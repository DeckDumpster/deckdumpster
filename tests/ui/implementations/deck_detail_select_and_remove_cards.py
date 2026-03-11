"""
Hand-written implementation for deck_detail_select_and_remove_cards.

Switches to sideboard zone, selects all cards, removes them, and verifies
the zone is now empty.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for the deck to load
    harness.wait_for_text("Bolt Tribal")

    # Switch to Sideboard tab
    harness.click_by_text("Sideboard")

    # Wait for sideboard cards to load
    harness.wait_for_text("Condemn")

    # Select all cards using the select-all checkbox
    harness.click_by_selector("#select-all")

    # Click Remove Selected
    harness.click_by_text("Remove Selected")

    # Wait for the table to refresh with empty zone
    harness.wait_for_text("No cards in this zone")

    # Verify sideboard count is now 0
    harness.assert_text_present("(0)")

    harness.screenshot("final_state")
