"""
Hand-written implementation for binders_manage_from_card_modal.

Assigns an unassigned card to a binder from the card detail modal
on the collection page. Uses Orazca Puzzle-Door (LCI) which is unassigned
and not used by any other test.
"""


def steps(harness):
    # Search for an unassigned card.
    harness.fill_by_placeholder("Search cards...", "Orazca")
    # Wait for search results to render.
    harness.wait_for_visible("tr[data-idx]")
    # Switch to grid view so we can click the card directly.
    harness.click_by_selector("#view-grid-btn")
    # Click the card in grid view.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal to appear.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    # Wait for the binder dropdown to appear (copies section loads async).
    harness.wait_for_visible("select.copy-add-to-binder", timeout=10_000)
    # Assign to Trade Binder using the dropdown.
    harness.select_by_label("select.copy-add-to-binder", "Trade Binder")
    harness.screenshot("final_state")
