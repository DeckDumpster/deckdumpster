"""
Hand-written implementation for decks_exclusivity_enforcement.

Assigns an unassigned copy of Scrawling Crawler to Trade Binder.
Scrawling Crawler has 3 copies: 2 in Bolt Tribal, 1 unassigned (#3).
"""


def steps(harness):
    # Search for Scrawling Crawler on the collection page.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Scrawling Crawler")
    # Wait for results and switch to grid view.
    harness.wait_for_visible("tr[data-idx]")
    harness.click_by_selector("#view-grid-btn")
    # Click the card in grid view.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal and copies to load.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=10_000)
    harness.wait_for_text("Copies")
    # Assign the unassigned copy to Trade Binder.
    harness.select_by_label("select.copy-add-to-binder", "Trade Binder")
    harness.screenshot("final_state")
