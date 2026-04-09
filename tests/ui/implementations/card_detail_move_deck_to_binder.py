"""
Hand-written implementation for card_detail_move_deck_to_binder.

Moves a copy from a deck to a binder and verifies the post-move UI state.
"""


def steps(harness):
    # start_page: /card/fdn/100 — auto-navigated by test runner.
    harness.wait_for_text("Beast-Kin Ranger")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=500)
    # Verify the copy is currently in deck "Bolt Tribal".
    harness.assert_text_present("Bolt Tribal")
    harness.assert_visible(".copy-remove-deck")
    # Select "Foil Collection" from the "Move to Binder" dropdown.
    harness.select_by_label(".copy-move-to-binder", "Foil Collection")
    # The copies section reloads showing the binder name.
    harness.wait_for_text("Foil Collection", timeout=500)
    harness.assert_text_present("Foil Collection")
    # A "Remove" link for the binder should appear.
    harness.assert_visible(".copy-remove-binder")
    harness.screenshot("final_state")
