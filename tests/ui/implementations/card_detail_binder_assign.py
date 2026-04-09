"""
Hand-written implementation for card_detail_binder_assign.

Assigns an unassigned copy to a binder from the card detail page and
verifies the post-assignment UI state.
"""


def steps(harness):
    # start_page: /card/mkm/210 — auto-navigated by test runner.
    harness.wait_for_text("Judith, Carnage Connoisseur")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=500)
    # Verify the copy is currently unassigned.
    harness.assert_text_present("Unassigned")
    # Select "Trade Binder" from the "Add to Binder" dropdown.
    harness.select_by_label(".copy-add-to-binder", "Trade Binder")
    # The copies section reloads showing the binder name.
    harness.wait_for_text("Trade Binder", timeout=500)
    harness.assert_text_present("Trade Binder")
    # A "Remove" link should appear.
    harness.assert_visible(".copy-remove-binder")
    harness.screenshot("final_state")
