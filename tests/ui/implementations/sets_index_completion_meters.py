"""
Hand-written implementation for sets_index_completion_meters.

A meter is a fraction, so it is drawn only when there is something to be a
fraction of. Seventeen of the fixture's eighteen cached sets store a base
boundary and draw both meters; spg stores none — MTGJSON reports baseSetSize 0
for Special Guests — and must draw only the all-printings one rather than
render 0 / 0 as NaN%.

Both states in one page is the point: before de-1ov the fixture reached only
the hidden case, so nothing here could tell a correctly hidden meter from a
meter that never renders.
"""


def steps(harness):
    harness.assert_element_count("a.set-tile", 18)

    # 17 sets with a stored boundary draw two meters, spg draws one: 35.
    harness.assert_element_count("div.set-meter", 35)
    # The base meter is always drawn first inside .set-meters, so an adjacent
    # pair is exactly a tile showing both — one per set that has a boundary.
    harness.assert_element_count("div.set-meter + div.set-meter", 17)

    # The failure this replaces: 0 / 0 rendered as a percentage.
    harness.assert_text_absent("NaN")

    # The populated case. Both meters are real fractions with real bars, and
    # the base one is a fraction of the base set (291), not of the whole
    # printing list (771) — the two must not be the same number.
    harness.assert_visible("a.set-tile[href='/sets/fdn'] span.set-meter-fill")
    assert _meters(harness, "fdn") == [("Set", "12 / 291"), ("All", "12 / 771")]

    # The hidden case, still on the same page: one meter, and it is the
    # all-printings one.
    assert _meters(harness, "spg") == [("All", "1 / 165")]

    harness.screenshot("final_state")


def _meters(harness, set_code):
    """(label, count) per meter on one tile, in the order they are drawn.

    Read from the label and count spans rather than the meter's innerText:
    innerText inserts a line break only where the tile happens to wrap, so
    "Set 12 / 291" and "All1 / 165" come back from the same markup.
    """
    return [
        tuple(pair)
        for pair in harness.page.eval_on_selector_all(
            f"a.set-tile[href='/sets/{set_code}'] div.set-meter",
            "els => els.map(e => ["
            "  e.querySelector('.set-meter-label').textContent.trim(),"
            "  e.querySelector('.set-meter-count').textContent.trim(),"
            "])",
        )
    ]
