"""
Hand-written implementation for deck_detail_delete_redirects_to_list.

Creates a throwaway deck, navigates to its detail page, deletes it,
and verifies the browser redirects back to the deck list.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for page to load
    harness.wait_for_text("New Deck")

    # Create a throwaway deck
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")
    harness.fill_by_selector("#f-name", "Deck To Delete")
    harness.click_by_text("Save")

    # Wait for redirect to the new deck's detail page
    harness.wait_for_visible("#deck-name")
    harness.assert_text_present("Deck To Delete")

    # Accept the upcoming confirmation dialog
    harness.page.on("dialog", lambda dialog: dialog.accept())

    # Click Delete Deck
    harness.click_by_text("Delete Deck")

    # Wait for redirect back to deck list
    harness.wait_for_text("New Deck")

    # Verify we're back on the list page
    harness.assert_text_present("Bolt Tribal")

    # Verify the deleted deck is gone
    harness.assert_text_absent("Deck To Delete")

    harness.screenshot("final_state")
