"""
Hand-written implementation for sets_index_completion_sort.

Switches the Sort control to Completion and back, pinning the three things the
mode changes: the type blocks dissolve into one grid, the sets nothing is owned
from leave it, and what remains runs fullest-first.

Which sets are dropped is asserted as a plain element count, not a
`:not([hidden])` one — the sort removes them from the DOM, where the filter
only hides. Whether the order is by fraction or by owned count is invisible
here: the fixture's fullest set is also its most-owned one, so
`tests/test_sets_page.py` pins that against a synthetic payload instead.
"""

SORT = "#sets-sort"


def steps(harness):
    # The default view: every cached set, in five set_type blocks.
    harness.assert_element_count("a.set-tile", 18)
    harness.assert_element_count("section.set-group[data-set-type]", 5)
    harness.assert_element_count("section.set-group[data-sort='completion']", 0)
    harness.assert_text_present("18 sets")

    harness.select_by_label(SORT, "Completion")

    # The grouping dissolves — one grid, and not one of the type blocks left.
    harness.assert_element_count("section.set-group[data-set-type]", 0)
    harness.assert_element_count("#sets-body section.set-group", 1)
    harness.assert_visible("section.set-group[data-sort='completion']")
    # The heading names the population, so nine sets going missing reads as the
    # point of the mode rather than as a page that lost half its content.
    harness.assert_text_present("Owned sets")

    # Only the sets with a card in them. j25 is cached and has a tile in the
    # default view; here it has none at all.
    harness.assert_element_count("a.set-tile:not([hidden])", 9)
    harness.assert_text_present("9 sets")
    harness.assert_element_count("a.set-tile[href='/sets/j25']", 0)

    # Fullest first: Foundations at 12 of 771 leads.
    harness.assert_element_count(
        "section[data-sort='completion'] a.set-tile:first-child[href='/sets/fdn']", 1
    )

    # Switching back restores the blocks and every set.
    harness.select_by_label(SORT, "Release date")
    harness.assert_element_count("section.set-group[data-set-type]", 5)
    harness.assert_element_count("a.set-tile:not([hidden])", 18)
    harness.assert_text_present("18 sets")
    harness.screenshot("final_state")
