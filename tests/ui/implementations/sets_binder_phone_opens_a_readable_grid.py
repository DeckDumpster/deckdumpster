"""
Hand-written implementation for sets_binder_phone_opens_a_readable_grid.

Reads the opening cards-per-row at desktop width, then at phone width, and
checks the grid really draws that many across rather than only saying so.
"""

PHONE = {"width": 390, "height": 844}


def _tracks(harness):
    """How many columns the grid is actually laid out in — the thing on screen,
    as opposed to #col-count, which is a label that claims to describe it."""
    return harness.page.evaluate(
        "getComputedStyle(document.querySelector('.card-grid'))"
        ".gridTemplateColumns.trim().split(/\\s+/).length"
    )


def steps(harness):
    # start_page: /sets/spg — auto-navigated by the test runner at 1280x900.
    harness.wait_for_text("165 printings", timeout=5_000)

    # The desktop reading is unchanged: six across, and the default stays out
    # of the URL.
    assert harness.page.inner_text("#col-count").strip() == "6"
    assert _tracks(harness) == 6
    harness.screenshot("desktop")

    # That load wrote setsGridCols=6, which is precisely what a phone opening
    # this page for the first time does not have. Clearing it is what makes the
    # next navigation a first visit rather than an inherited one — without it
    # the page reads 6 back out of storage and never reaches the default at all.
    harness.page.evaluate("localStorage.removeItem('setsGridCols')")

    # Resize BEFORE navigating: storedCols() reads innerWidth once, at load.
    harness.page.set_viewport_size(PHONE)
    harness.navigate("/sets/spg")
    harness.wait_for_text("165 printings", timeout=5_000)

    # Three across — the value /sheets picks, and readable at this width where
    # six is not.
    assert harness.page.inner_text("#col-count").strip() == "3", (
        f"Phone opened at {harness.page.inner_text('#col-count').strip()} "
        f"cards per row, expected 3"
    )
    tracks = _tracks(harness)
    assert tracks == 3, f"Grid is {tracks} wide at 390px, expected 3"

    harness.screenshot("final_state")
