"""
Hand-written implementation for collection_filter_rarity.

Opens the filter sidebar and applies rarity filters to the collection.
"""


def steps(harness):
    # Navigate to Collection page (default is table view)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Click the mythic rarity filter label (checkbox inputs are display:none)
    harness.click_by_selector("label[for='rf-mythic']")

    # Screenshot filtered state
    harness.screenshot("mythic_filtered")

    # Clear all filters
    harness.click_by_selector("#clear-filters-btn")

    # Close sidebar
    harness.click_by_selector("#sidebar-close-btn")

    harness.screenshot("final_state")
