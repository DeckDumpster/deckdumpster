"""
Hand-written implementation for collection_inline_deck_creation.

Creates a new deck inline from the card modal's per-copy "Add to Deck"
dropdown using the "New Deck..." option. Uses Cathar Commando (FDN 139)
which is unassigned. The prompt dialog is auto-accepted with "Test View"
by the test harness.
"""


def steps(harness):
    # Search for an unassigned card.
    harness.fill_by_placeholder("Search cards...", "Cathar Commando")
    # Wait for results and switch to grid view.
    harness.wait_for_visible("tr[data-idx]")
    harness.click_by_selector("#view-grid-btn")
    # Click the card in grid view.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal and copies to load.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=500)
    harness.wait_for_visible("select.copy-add-to-deck", timeout=500)
    # Select "New Deck..." — the prompt auto-accepts with "Test View".
    harness.select_by_label("select.copy-add-to-deck", "New Deck...")
    # Wait for the assignment to complete — the copy section re-renders
    # showing a "Remove" link instead of the "Add to Deck" dropdown.
    harness.wait_for_visible(".copy-remove-deck", timeout=500)
    harness.screenshot("final_state")
