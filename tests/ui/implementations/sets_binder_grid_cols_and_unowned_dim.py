"""
Hand-written implementation for sets_binder_grid_cols_and_unowned_dim.

Loads spg's binder page at cols=3 and verifies the grid really lays out three
to a row, that the 164 empty pockets are visibly dimmed, and that the one
owned card is not.
"""


def steps(harness):
    # start_page: /sets/spg?cols=3 — auto-navigated by test runner.

    # #status is written after the render loop, so the count is what says the
    # grid is finished rather than half-painted. 5 s because this is the page
    # load; every assertion below keeps the 500 ms interaction budget.
    harness.wait_for_text("165 printings", timeout=5_000)

    # The fixture records no base_set_size, so the whole set is one contiguous
    # run — every pre-2019 set's shape, and the NULL degradation the endpoint
    # documents.
    harness.assert_text_present("Base set")

    # Cards-per-row, checked on the layout rather than the label: one grid
    # track per column, so a count of three is the row actually being three
    # wide. #col-count only says what the control believes.
    tracks = harness.page.evaluate(
        "getComputedStyle(document.querySelector('.card-grid'))"
        ".gridTemplateColumns.trim().split(/\\s+/).length"
    )
    assert tracks == 3, f"Expected 3 grid columns at cols=3, got {tracks}"
    assert harness.page.inner_text("#col-count").strip() == "3"

    # Exactly one pocket in spg is filled in the fixture; everything else is
    # empty and must carry the dim.
    harness.assert_element_count(".sheet-card:not(.unowned)", 1)
    harness.assert_element_count(".sheet-card.unowned", 164)

    # The dim is a visible difference, not just a class: the empty pockets
    # compute a grayscale filter and the owned one computes none.
    dimmed = harness.page.evaluate(
        "getComputedStyle(document.querySelector"
        "('.sheet-card.unowned .sheet-card-img-wrap')).filter"
    )
    assert "grayscale" in dimmed, f"Unowned tile is not dimmed: filter={dimmed!r}"
    owned = harness.page.evaluate(
        "getComputedStyle(document.querySelector"
        "('.sheet-card:not(.unowned) .sheet-card-img-wrap')).filter"
    )
    assert "grayscale" not in owned, f"Owned tile is dimmed: filter={owned!r}"

    harness.screenshot("final_state")
