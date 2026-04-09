"""
Hand-written implementation for collection_wishlist_panel.

Opens the wishlist panel from the More menu, verifies entries are shown,
removes one entry, and closes the panel via the backdrop.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Open the more menu and click Wishlist
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#wishlist-toggle-btn")

    # Wait for the wishlist panel to slide in
    harness.wait_for_visible("#wishlist-panel")
    harness.assert_text_present("Disruptor Flute")
    harness.screenshot("wishlist_open")

    # Remove the first wishlist entry
    harness.click_by_selector(".wl-remove")

    # Close panel via backdrop
    harness.click_by_selector("#wishlist-backdrop")
    harness.wait_for_hidden("#wishlist-panel.open")

    harness.screenshot("final_state")
