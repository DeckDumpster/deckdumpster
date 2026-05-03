"""
Hand-written implementation for collection_multiselect_delete_individual_copies.

Enables multi-select on the collection page, searches for Unstoppable Slasher
(2 copies), selects one, deletes it, and verifies only 1 copy remains.
"""


def steps(harness):
    # Navigate and search for Unstoppable Slasher
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Unstoppable Slasher")
    harness.wait_for_visible("tr[data-idx]")

    # Enable multi-select (triggers re-fetch with expand=copies)
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")

    # Wait for expanded rows — should be 2 individual copies
    harness.wait_for_visible("tr[data-idx]")
    harness.screenshot("two_individual_copies")

    # Select first checkbox only
    harness.click_by_selector("tr[data-idx]:first-child input.row-sel-cb")

    # Click delete (confirm dialog auto-accepted)
    harness.click_by_selector("#sel-delete-btn")

    # Wait for re-fetch — should be 1 copy remaining
    harness.wait_for_text("1 card")

    harness.screenshot("final_state")
