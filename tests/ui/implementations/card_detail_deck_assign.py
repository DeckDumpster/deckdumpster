"""
Hand-written implementation for card_detail_deck_assign.

Assigns an unassigned copy to a deck. Since no decks exist in the default
demo data, creates one via fetch API first, then re-navigates to pick up
the dropdown option.
"""


def steps(harness):
    # start_page: /card/woe/56 — auto-navigated by test runner.
    harness.wait_for_text("Ingenious Prodigy")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=10_000)
    # Verify the copy is currently unassigned.
    harness.assert_text_present("Unassigned")
    # Create a deck via API (no decks exist in demo data).
    harness.page.evaluate(
        "fetch('/api/decks', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({name: 'Bolt Tribal'})})"
    )
    harness.page.wait_for_timeout(500)
    # Re-navigate to pick up the new deck in the dropdown.
    harness.navigate("/card/woe/56")
    harness.wait_for_visible(".copy-section", timeout=10_000)
    # Select the deck from the "Add to Deck" dropdown.
    harness.select_by_label(".copy-add-to-deck", "Bolt Tribal")
    # The copy section reloads showing the deck name.
    harness.wait_for_text("Bolt Tribal", timeout=10_000)
    harness.assert_text_present("Bolt Tribal")
    # A "Remove" link should appear.
    harness.assert_visible(".copy-remove-deck")
    harness.screenshot("final_state")
