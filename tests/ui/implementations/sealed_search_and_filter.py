"""
Hand-written implementation for sealed_search_and_filter.

Searches for "Bloomburrow" to filter sealed products, then uses the
category filter sidebar to filter by "Booster Pack".
"""


def steps(harness):
    # Wait for sealed products to load
    harness.wait_for_visible("[data-uuid]")

    # Search for Bloomburrow using the search input
    harness.fill_by_selector("#search-input", "Bloomburrow")
    harness.wait_for_text("Bloomburrow")
    harness.screenshot("search_bloomburrow")

    # Clear search
    harness.fill_by_selector("#search-input", "")

    # Wait for async filtering to complete

    # Open filter sidebar
    harness.click_by_selector("#filter-btn")
    harness.wait_for_visible("#sidebar.open")

    # Click the Booster Pack category pill (checkbox is display:none)
    harness.click_by_selector("label[for='cat-booster_pack']")
    harness.screenshot("category_filtered")

    # Clear filters
    harness.click_by_selector("#clear-filters-btn")

    # Close sidebar by clicking the backdrop
    harness.click_by_selector("#sidebar-backdrop")

    harness.screenshot("final_state")
