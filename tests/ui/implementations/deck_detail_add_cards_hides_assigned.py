"""
Hand-written implementation for deck_detail_add_cards_hides_assigned.

Opens deck 2 picker, searches for a fully-assigned card (Condemn) and
verifies the empty state, then searches for a partially-assigned card
(Unstoppable Slasher) and verifies only the unassigned copy appears.
"""


def steps(harness):
    # Navigate to deck 2
    harness.navigate("/decks/2")
    harness.wait_for_text("Eldrazi Ramp")

    # Open add-cards modal via button
    harness.click_by_selector("#add-card-btn")
    harness.wait_for_visible("#add-cards-modal.active")

    # Search for Condemn — all copies are in deck 1
    harness.fill_by_placeholder("Search by name...", "Condemn")
    harness.wait_for_text("No unassigned copies found")
    harness.screenshot("condemn_no_unassigned")

    # Clear and search for Unstoppable Slasher — 1 in binder, 1 unassigned
    harness.fill_by_placeholder("Search by name...", "Unstoppable")
    harness.wait_for_text("Unstoppable Slasher")

    # Only the unassigned copy should appear
    harness.assert_element_count(".picker-card", 1)

    harness.screenshot("final_state")
