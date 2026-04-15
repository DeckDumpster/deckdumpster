"""
Hand-written implementation for collection_more_menu_in_viewport.

Opens the More (vertical-ellipsis) menu on the collection page and
verifies its items are visible and readable. Guards against regressions
of the CSS fix that switched the panel from right-anchored (which
clipped off-screen) to left-anchored.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Open the More menu
    harness.click_by_selector("#more-menu-btn")
    harness.wait_for_visible("#more-menu-dropdown.open")

    # The four item labels inside the panel must be visible and readable
    harness.assert_text_present("Toggle Multi-Select")
    harness.assert_text_present("Image Display")
    harness.assert_text_present("Saved Views")
    harness.assert_visible("#wishlist-toggle-btn")
    harness.assert_visible("#toggle-multiselect-btn")

    # Click an item inside the panel — Playwright will error if the
    # element is not actually hit-testable, proving the panel is on-screen
    harness.click_by_selector("#toggle-multiselect-btn")
    harness.wait_for_visible("#selection-bar")

    harness.screenshot("final_state")
