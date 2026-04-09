"""
Hand-written implementation for collection_multiselect_new_deck.

Multi-selects a card and creates a new deck inline via the assign modal's
"New Deck..." option. Uses Ruby Medallion (MH3 295) which is
unassigned. The prompt dialog is auto-accepted with "Test View".
"""


def steps(harness):
    # Search for an unassigned card.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Ruby Medallion")
    harness.wait_for_visible("tr[data-idx]")
    # Open the more menu and enable multi-select.
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")
    # Select the card via its checkbox in the table row.
    harness.click_by_selector("tr[data-idx] input.row-sel-cb")
    # Click "Add to Deck" in the selection bar.
    harness.click_by_selector("#sel-deck-btn")
    # Wait for the assign overlay to appear.
    harness.wait_for_visible("#assign-deck-overlay", timeout=500)
    # Select "New Deck..." — the prompt auto-accepts with "Test View".
    harness.select_by_label("#assign-deck-select", "New Deck...")
    # Click the Add button to confirm.
    harness.click_by_text("Add", exact=True)
    # Wait for the overlay to close.
    harness.wait_for_hidden("#assign-deck-overlay", timeout=500)
    harness.screenshot("final_state")
