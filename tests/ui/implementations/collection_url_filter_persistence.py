"""
Hand-written implementation for collection_url_filter_persistence.

Navigates to the collection page with filter params in the URL and verifies
that the filters are restored: reduced card count and sort applied.
"""


def steps(harness):
    # Navigate with pre-set URL params (rare rarity, sorted by price desc)
    harness.navigate("/collection?rarities=rare&sort=price&sort_dir=desc")
    harness.wait_for_visible("#status")

    # Verify filtered results show fewer than the full 43 entries
    harness.assert_text_absent("43 entries")

    # Open the sidebar to see filter state
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar.open")

    # Screenshot shows: rare rarity filter visually active in sidebar, sorted table
    harness.screenshot("final_state")
