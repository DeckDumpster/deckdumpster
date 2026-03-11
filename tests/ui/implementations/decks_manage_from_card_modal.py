"""
Hand-written implementation for decks_manage_from_card_modal.

Assigns an unassigned card to a deck from the card detail modal.
Uses Cathar Commando (FDN 139) which is owned and unassigned in the fixture.
"""


def steps(harness):
    # Search for an unassigned owned card.
    harness.fill_by_placeholder("Search cards...", "Cathar Commando")
    # Wait for results and switch to grid view.
    harness.wait_for_visible("tr[data-idx]")
    harness.click_by_selector("#view-grid-btn")
    # Click the card in grid view.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal and copies to load.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    harness.wait_for_visible("select.copy-add-to-deck", timeout=10_000)
    # Assign to Bolt Tribal deck using the dropdown.
    harness.select_by_label("select.copy-add-to-deck", "Bolt Tribal")
    harness.screenshot("final_state")
