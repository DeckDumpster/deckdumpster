"""
Hand-written implementation for decks_delete_keeps_cards.

Deletes the "Eldrazi Ramp" deck, then navigates to the collection
page and searches for "Disruptor Flute" to verify it's still there.
"""


def steps(harness):
    # Click on the Eldrazi Ramp deck card to open detail view.
    harness.click_by_text("Eldrazi Ramp")
    # Click "Delete Deck" — the dialog handler auto-accepts confirms.
    harness.click_by_text("Delete Deck")
    # Navigate to collection to verify cards remain.
    harness.navigate("/collection")
    harness.fill_by_placeholder("Search cards...", "Disruptor Flute")
    harness.wait_for_text("Disruptor Flute")
    harness.screenshot("final_state")
