"""
Hand-written implementation for collection_sort_table_columns.

Clicks table column headers to sort the collection and verifies
the sort direction arrow changes.
"""


def steps(harness):
    # Navigate to Collection page (default is table view, sorted by name asc)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Click the Name column header to reverse sort (now descending)
    harness.click_by_selector("th[data-col='name']")
    harness.screenshot("name_desc")

    # Click the Set column header to sort by set ascending
    harness.click_by_selector("th[data-col='set']")
    harness.screenshot("final_state")
