"""
Hand-written implementation for collection_filter_color.

Opens the filter sidebar and selects a color pill to filter the collection.
Uses green (G) which has 12 cards in the fixture for clear visual feedback.
"""


def steps(harness):
    # Navigate to Collection page (default is table view)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Click the green color filter label (checkbox inputs are display:none)
    harness.click_by_selector("label[for='cf-G']")
    harness.screenshot("green_filtered")

    # Clear all filters
    harness.click_by_selector("#clear-filters-btn")

    # Close sidebar
    harness.click_by_selector("#sidebar-close-btn")

    harness.screenshot("final_state")
