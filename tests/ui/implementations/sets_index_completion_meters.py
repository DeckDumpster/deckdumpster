"""
Hand-written implementation for sets_index_completion_meters.

A meter is a fraction, so it is drawn only when there is something to be a
fraction of. Every set in the fixture has base_set_size NULL, which makes
total_base NULL, which must hide the base meter — not render 0 / 0 as NaN%.

The fixture reaching only the NULL case is de-1ov; when that is fixed this
scenario should also assert a set that shows both meters.
"""


def steps(harness):
    harness.assert_element_count("a.set-tile", 18)

    # One meter per set: the all-printings one. None of the 18 has a stored
    # base_set_size, so none draws a base meter.
    harness.assert_element_count("div.set-meter", 18)
    # The base meter is always drawn first inside .set-meters, so an adjacent
    # pair is exactly a tile showing both — there must be none.
    harness.assert_element_count("div.set-meter + div.set-meter", 0)

    # The failure this replaces: 0 / 0 rendered as a percentage.
    harness.assert_text_absent("NaN")

    # The meter that is drawn is a real fraction with a real bar behind it.
    harness.assert_visible("a.set-tile[href='/sets/fdn'] span.set-meter-fill")
    harness.assert_text_present("12 / 771")

    harness.screenshot("final_state")
