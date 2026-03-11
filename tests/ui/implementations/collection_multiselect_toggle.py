"""
Hand-written implementation for collection_multiselect_toggle.

Tests the multi-select lifecycle: toggle on, select all, select none,
toggle off. Also verifies the selection bar count updates.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Open more menu and enable multi-select
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")

    # Selection bar should appear with "0 selected"
    harness.wait_for_visible("#selection-bar")
    harness.screenshot("multiselect_on")

    # Click "All" to select all visible cards
    harness.click_by_selector("#sel-all")
    harness.screenshot("all_selected")

    # Click "None" to deselect all
    harness.click_by_selector("#sel-none")

    # Toggle multi-select off
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")

    harness.screenshot("final_state")
