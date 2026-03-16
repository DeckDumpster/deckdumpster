"""
Generated from intent: decks_create_and_add_cards
Generated at: 2026-03-01T00:14:07Z
System version: d11cf4c
Intent hash: 4f24d502aca65742
"""


def steps(harness):
    harness.click_by_text("New Deck")
    harness.fill_by_placeholder("My Commander Deck", "Test Deck")
    harness.select_by_label("#f-format", "Commander / EDH")
    harness.click_by_text("Save")
    # After save, redirects to unified deck page
    harness.wait_for_visible(".deck-header h2")
    harness.click_by_selector("#add-card-btn")
    harness.fill_by_placeholder("Search by name...", "Cathar")
    harness.click_by_text("Cathar Commando")
    harness.click_by_text("Add Selected")
    harness.screenshot("final_state")
