"""
Hand-written implementation for collection_clear_filters_resets_url.

Loads the page with filters in the URL, clicks Clear Filters, and verifies
the full collection is shown.
"""


def steps(harness):
    # Navigate with filters pre-applied via URL
    harness.navigate("/collection?rarities=rare&q=art")
    harness.wait_for_visible("#status")

    # Verify we start with filtered results (not the full 43)
    harness.assert_text_absent("43 entries")

    # Open sidebar to access Clear Filters button
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar.open")

    # Click Clear Filters
    harness.click_by_selector("#clear-filters-btn")

    # Wait for full collection to reload
    harness.wait_for_text("43 entries")

    # Screenshot shows full unfiltered collection
    harness.screenshot("final_state")
