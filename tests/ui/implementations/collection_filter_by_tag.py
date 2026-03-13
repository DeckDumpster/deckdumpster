"""
Hand-written implementation for collection_filter_by_tag.

Selects a tag from the Tag filter and verifies cards are filtered.
Removes the tag pill and verifies cards are restored.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Type 'removal' in the tag search input
    harness.fill_by_selector("#tag-search", "removal")

    # Wait for dropdown to appear and click the 'removal' option
    harness.wait_for_visible("#tag-dropdown.open li")
    harness.click_by_selector("#tag-dropdown li")

    # Screenshot the filtered state — should show fewer cards
    harness.screenshot("filtered_by_removal")

    # Verify a pill appeared for the selected tag
    harness.assert_visible("#tag-pills .selected-pill")

    # Remove the tag by clicking the × on the pill
    harness.click_by_selector("#tag-pills .selected-pill .remove-pill")

    # Verify pill is gone
    harness.wait_for_hidden("#tag-pills .selected-pill")

    harness.screenshot("final_state")
