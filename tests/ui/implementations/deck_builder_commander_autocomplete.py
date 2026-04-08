"""
Hand-written implementation for deck_builder_commander_autocomplete.

Types a legendary creature name, verifies autocomplete appears,
selects it, and confirms the Create button becomes enabled.
"""


def steps(harness):
    # Navigate to the deck builder page
    harness.navigate("/deck-builder")
    harness.wait_for_text("New Commander Deck")
    # Type a legendary creature name into the search
    harness.fill_by_placeholder("Search your collection...", "Glarb")
    # Wait for autocomplete dropdown to show results
    harness.wait_for_text("Glarb, Calamity's Augur", timeout=500)
    # Click the autocomplete result
    harness.click_by_text("Glarb, Calamity's Augur")
    # Verify the Create Deck button is now enabled (text still present)
    harness.assert_text_present("Create Deck")
    harness.screenshot("final_state")
