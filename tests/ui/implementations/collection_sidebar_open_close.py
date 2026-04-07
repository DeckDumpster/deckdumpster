"""
Hand-written implementation for collection_sidebar_open_close.

Opens and closes the filter sidebar, verifying key filter dimensions
are present. Tests both the close button and backdrop close methods.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Verify key filter sections exist
    harness.assert_visible("#color-filters")
    harness.assert_visible("#rarity-filters")
    harness.assert_visible("#type-filters")
    harness.assert_visible("#set-filter-wrap")
    harness.screenshot("sidebar_open")

    # Close via close button
    harness.click_by_selector("#sidebar-close-btn")
    harness.wait_for_hidden("#sidebar.open")

    # Re-open and close via backdrop
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")
    harness.click_by_selector("#sidebar-backdrop")
    harness.wait_for_hidden("#sidebar.open")

    harness.screenshot("final_state")
