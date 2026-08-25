"""
Hand-written implementation for sets_index_filter_opens_a_collapsed_type.

A filter that matches inside a folded block opens it, so the count and the page
agree; clearing the filter hands every block back to the state it was in.

Two hiding mechanisms overlap here — the filter's `hidden` attribute on a tile
and the collapse's CSS class on the section — and a tile can be under both at
once. assert_hidden reads either, so it is what is used throughout.
"""

FILTER = "Filter by set name or code"
DRAFT_GRID = "section[data-set-type='draft_innovation'] .set-grid"


def steps(harness):
    # Draft Innovation is outside the top four ranks, so it arrives folded.
    harness.assert_hidden(DRAFT_GRID)
    harness.assert_hidden("a.set-tile[href='/sets/mh3']")
    harness.assert_element_count("#sets-rail .rail-row.is-empty", 0)

    harness.fill_by_placeholder(FILTER, "modern horizons")

    # The match is shown, not merely counted.
    harness.assert_visible(DRAFT_GRID)
    harness.assert_visible("a.set-tile[href='/sets/mh3']")
    harness.assert_hidden("a.set-tile[href='/sets/j25']")
    harness.assert_text_present("1 of 18 sets")

    # The rail recounts with the sections and says which rows go nowhere.
    harness.assert_element_count("#sets-rail .rail-row.is-empty", 4)
    harness.assert_element_count(
        "#sets-rail .rail-row[data-set-type='draft_innovation'].is-empty", 0
    )

    # Clearing puts the page back the way it was, folded block included.
    harness.fill_by_placeholder(FILTER, "")
    harness.assert_hidden(DRAFT_GRID)
    harness.assert_visible("section[data-set-type='expansion'] .set-grid")
    harness.assert_element_count("#sets-rail .rail-row.is-empty", 0)
    harness.assert_text_present("18 sets")

    harness.screenshot("final_state")
