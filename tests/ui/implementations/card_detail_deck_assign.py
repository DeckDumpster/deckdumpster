"""
Hand-written implementation for card_detail_deck_assign.

Assigns an unassigned copy to a deck. Uses Cathar Commando (FDN 139)
which is unassigned in the current fixture, and assigns it to the
existing "Bolt Tribal" deck.
"""


def steps(harness):
    # start_page: /card/fdn/139 — auto-navigated by test runner.
    harness.wait_for_text("Cathar Commando")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=500)
    # Verify the copy is currently unassigned.
    harness.assert_text_present("Unassigned")
    # Select "Bolt Tribal" from the "Add to Deck" dropdown.
    harness.select_by_label(".copy-add-to-deck", "Bolt Tribal")
    # The copy section reloads showing the deck name.
    harness.wait_for_text("Bolt Tribal", timeout=500)
    harness.assert_text_present("Bolt Tribal")
    # A "Remove" link should appear.
    harness.assert_visible(".copy-remove-deck")
    harness.screenshot("final_state")
