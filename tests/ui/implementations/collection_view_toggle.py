"""
Hand-written implementation for collection_view_toggle.

Toggles between table view (default) and grid view on the Collection page.
"""


def steps(harness):
    # Navigate to Collection page (default is table view)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")

    # Verify grid cards appear
    harness.wait_for_visible(".sheet-card")
    harness.screenshot("grid_view")

    # Switch back to table view
    harness.click_by_selector("#view-table-btn")

    # Verify table reappears
    harness.wait_for_visible(".collection-table")

    harness.screenshot("final_state")
