"""
Hand-written implementation for collection_deck_binder_filter.

Opens the sidebar, selects "Unassigned Only" from the container filter,
then switches back to "All Cards".
"""


def steps(harness):
    # Open the filter sidebar.
    harness.click_by_text("Filters")
    # Select "Unassigned Only" from the container filter dropdown.
    harness.select_by_label("#container-filter", "Unassigned Only")
    # Switch back to "All Cards".
    harness.select_by_label("#container-filter", "All Cards")
    harness.screenshot("final_state")
