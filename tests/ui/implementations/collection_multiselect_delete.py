"""
Hand-written implementation for collection_multiselect_delete.

Enters multi-select mode, selects an unassigned card, and deletes it.
Uses Graceful Takedown which is unassigned. The browser confirm dialog
is auto-accepted by the harness.
"""


def steps(harness):
    # Navigate and search for an unassigned card
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)
    harness.fill_by_placeholder("Search cards...", "Graceful Takedown")
    harness.wait_for_visible("tr[data-idx]")

    # Open more menu and enable multi-select
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")

    # Select the card via its checkbox
    harness.click_by_selector("tr[data-idx] input.row-sel-cb")

    # Click delete (confirm dialog auto-accepted)
    harness.click_by_selector("#sel-delete-btn")

    # Wait for card to be removed
    harness.wait_for_text("0 cards")

    harness.screenshot("final_state")
