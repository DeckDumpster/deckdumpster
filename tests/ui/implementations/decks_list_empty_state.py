"""
Hand-written implementation for decks_list_empty_state.

Deletes both fixture decks via the UI, then verifies the empty state message.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")
    harness.wait_for_text("Bolt Tribal")

    # Delete deck 1: click into it, then delete
    harness.click_by_text("Bolt Tribal")
    harness.wait_for_visible("#deck-name")
    harness.click_by_text("Delete Deck")

    # After deletion, we're redirected back to /decks
    harness.wait_for_text("Eldrazi Ramp")

    # Delete deck 2: click into it, then delete
    harness.click_by_text("Eldrazi Ramp")
    harness.wait_for_visible("#deck-name")
    harness.click_by_text("Delete Deck")

    # After deletion, we're back on /decks with no decks
    harness.wait_for_text("No decks yet")

    # Verify empty state message
    harness.assert_text_present("No decks yet")

    # Verify New Deck button is still available
    harness.assert_text_present("New Deck")

    harness.screenshot("final_state")
