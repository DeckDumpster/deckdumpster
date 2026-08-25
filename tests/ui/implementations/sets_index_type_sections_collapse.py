"""
Hand-written implementation for sets_index_type_sections_collapse.

Walks the default expand state and the header toggle.

A collapsed section keeps its tiles in the DOM — the grid is `display: none`,
not a removal — so everything here is asserted with assert_visible /
assert_hidden. A ':not([hidden])' count would read every collapsed tile as
present, because that attribute belongs to the filter, not to the collapse.
"""

# The label appears twice on the page: as a rail row and as the group heading,
# and the rail is first in document order. click_by_text would hit the rail.
MASTERPIECE_HEADER = "section[data-set-type='masterpiece'] h2"


def steps(harness):
    # Expansion and Core are the fixture's only types inside the top four of
    # SET_TYPE_RANK, so they are the two that start open.
    harness.assert_visible("section[data-set-type='expansion'] .set-grid")
    harness.assert_visible("section[data-set-type='core'] .set-grid")
    harness.assert_hidden("section[data-set-type='draft_innovation'] .set-grid")
    harness.assert_hidden("section[data-set-type='masterpiece'] .set-grid")
    harness.assert_hidden("section[data-set-type='duel_deck'] .set-grid")

    # A tile in an open block is on screen; one in a folded block is not, but is
    # still in the DOM.
    harness.assert_visible("a.set-tile[href='/sets/ecl']")
    harness.assert_hidden("a.set-tile[href='/sets/ddh']")
    harness.assert_element_count("a.set-tile", 18)

    # The folded heading still says what is inside it.
    harness.assert_visible("section[data-set-type='masterpiece'] .group-owned")

    # Opening one block leaves the others alone.
    harness.click_by_selector(MASTERPIECE_HEADER)
    harness.assert_visible("section[data-set-type='masterpiece'] .set-grid")
    harness.assert_visible("a.set-tile[href='/sets/spg']")
    harness.assert_visible("section[data-set-type='expansion'] .set-grid")

    # And it folds back.
    harness.click_by_selector(MASTERPIECE_HEADER)
    harness.assert_hidden("section[data-set-type='masterpiece'] .set-grid")
    harness.assert_hidden("a.set-tile[href='/sets/spg']")

    harness.screenshot("final_state")
