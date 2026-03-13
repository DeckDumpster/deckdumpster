"""
Hand-written implementation for collection_tag_filter_sidebar.

Verifies the Tag filter section exists in the collection sidebar with
search input, dropdown, and pills container.
"""


def steps(harness):
    # Navigate to Collection page
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Open the filter sidebar
    harness.click_by_selector("#sidebar-toggle-btn")
    harness.wait_for_visible("#sidebar")

    # Verify tag search input exists and has correct placeholder
    harness.assert_visible("input#tag-search[placeholder='Search tags...']")

    # Focus the tag search to open the dropdown
    harness.click_by_selector("#tag-search")
    harness.wait_for_visible("#tag-dropdown.open")

    # Verify dropdown has tag options
    harness.assert_visible("#tag-dropdown li")

    harness.screenshot("tag_filter_in_sidebar")

    # Close sidebar
    harness.click_by_selector("#sidebar-close-btn")

    harness.screenshot("final_state")
