"""
Hand-written implementation for sets_homepage_nav_link.

Navigates from the homepage to the set index via the Analysis-group nav link.
"""


def steps(harness):
    # Start on the homepage
    harness.navigate("/")
    # Verify the Browse Sets nav link is visible, subtitle and all
    harness.assert_visible("a[href='/sets']")
    harness.assert_text_present("Browse Sets")
    harness.assert_text_present("Every set as a binder grid, with completion")

    # Click the Browse Sets nav link
    harness.click_by_text("Browse Sets")

    # The index is populated from /api/sets/index, so the first tile is what
    # says the page arrived — it renders no heading of its own.
    harness.wait_for_visible("#sets-body a.set-tile")
    harness.assert_element_count("a.set-tile", 18)
    harness.assert_text_present("18 sets")

    # Each tile is a link into that set's binder page.
    harness.assert_visible("a.set-tile[href='/sets/ecl']")
    harness.screenshot("final_state")
