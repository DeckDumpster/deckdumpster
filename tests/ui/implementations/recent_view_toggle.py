"""
Hand-written implementation for recent_view_toggle.

Toggles between table view (default) and grid view on the Recent Images page.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")
    harness.wait_for_visible(".img-card")

    # Default view is table mode — verify info rows are visible
    harness.assert_visible(".info-row")
    harness.screenshot("table_view")

    # Click view toggle to switch to grid mode
    harness.click_by_selector("#view-toggle")

    # In grid mode, card images (not info-rows) should be visible
    harness.wait_for_visible(".img-card > img")

    harness.screenshot("final_state")
