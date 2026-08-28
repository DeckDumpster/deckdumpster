"""
Hand-written implementation for sets_binder_phone_default_yields_to_my_choice.

Opens the binder at phone width, widens it, and comes back to the bare URL to
check the choice survived — the narrow default is a starting point, not a
preference that re-asserts itself every visit.
"""

PHONE = {"width": 390, "height": 844}


def _tracks(harness):
    return harness.page.evaluate(
        "getComputedStyle(document.querySelector('.card-grid'))"
        ".gridTemplateColumns.trim().split(/\\s+/).length"
    )


def steps(harness):
    # start_page: /sets/spg — auto-navigated by the test runner at 1280x900.
    harness.wait_for_text("165 printings", timeout=5_000)

    # Make the next navigation a first phone visit: drop the key the desktop
    # load just wrote, then resize before navigating (innerWidth is read once,
    # at load).
    harness.page.evaluate("localStorage.removeItem('setsGridCols')")
    harness.page.set_viewport_size(PHONE)
    harness.navigate("/sets/spg")
    harness.wait_for_text("165 printings", timeout=5_000)
    assert harness.page.inner_text("#col-count").strip() == "3"

    # I would rather see more of the set at once.
    harness.click_by_selector("#col-plus")
    harness.click_by_selector("#col-plus")
    harness.page.wait_for_timeout(300)
    assert harness.page.inner_text("#col-count").strip() == "5"
    harness.screenshot("widened")

    # Come back the way a return visit arrives: the bare address, no query
    # string carrying the answer.
    harness.navigate("/sets/spg")
    harness.wait_for_text("165 printings", timeout=5_000)

    assert harness.page.inner_text("#col-count").strip() == "5", (
        "The narrow default overwrote a choice that had already been made"
    )
    tracks = _tracks(harness)
    assert tracks == 5, f"Grid came back {tracks} wide, expected the chosen 5"

    harness.screenshot("final_state")
