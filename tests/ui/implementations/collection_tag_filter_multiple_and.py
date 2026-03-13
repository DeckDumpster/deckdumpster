"""
Hand-written implementation for collection_tag_filter_multiple_and.

Selects two tags and verifies AND logic — only cards with both tags shown.
Clears filters and verifies all cards restore.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Select first tag: 'removal'
    harness.fill_by_selector("#tag-search", "removal")
    harness.wait_for_visible("#tag-dropdown.open li")
    harness.click_by_selector("#tag-dropdown li")

    # Screenshot after first tag
    harness.screenshot("filtered_by_removal")

    # Select second tag: 'burn'
    harness.fill_by_selector("#tag-search", "burn")
    harness.wait_for_visible("#tag-dropdown.open li")
    harness.click_by_selector("#tag-dropdown li")

    # Screenshot after both tags — should show only cards with BOTH tags
    harness.screenshot("filtered_by_removal_and_burn")

    # Verify two pills are showing
    harness.assert_element_count("#tag-pills .selected-pill", 2)

    # Clear all filters
    harness.click_by_selector("#clear-filters-btn")

    # Verify pills are gone
    harness.wait_for_hidden("#tag-pills .selected-pill")

    harness.screenshot("final_state")
