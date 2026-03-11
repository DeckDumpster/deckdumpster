"""
Hand-written implementation for views_container_only_filter.

Loads the "Unassigned Cards" saved view which has container=unassigned
and an empty search query. Previously this did nothing because the
view-select handler only called fetchCollection() when f.q was truthy.
Verifies that unassigned cards appear and assigned cards do not.
"""


def steps(harness):
    # Open the filter sidebar.
    harness.click_by_text("Filters")
    # Select the "Unassigned Cards" saved view from the dropdown.
    harness.select_by_label("#view-select", "Unassigned Cards")
    # Wait for the collection to re-render with the container filter applied.
    # Cathar Commando is unassigned in the current fixture.
    harness.wait_for_text("Cathar Commando", timeout=10_000)
    # Verify the container filter dropdown was set correctly.
    harness.assert_visible("#container-filter")
    # Verify an assigned card (Acrobatic Cheerleader, in Trade Binder) is absent.
    harness.assert_text_absent("Acrobatic Cheerleader")
    # Verify an unassigned card is present.
    harness.assert_text_present("Cathar Commando")
    harness.screenshot("final_state")
