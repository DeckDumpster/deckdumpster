"""
Hand-written implementation for sets_index_completion_sort_keeps_filter.

The sort re-renders the whole grid; the filter box is not part of what it
re-renders. This walks a filter across a sort change and then keeps typing,
which is what catches a render that left the filter pointed at the grid it
replaced.

Filtered-out tiles keep the `hidden` attribute and stay in the DOM, so counts
here use `:not([hidden])` rather than text absence.
"""

FILTER = "Filter by set name or code"


def steps(harness):
    # Two sets are named Foundations, out of the 18 cached ones.
    harness.fill_by_placeholder(FILTER, "foundations")
    harness.assert_element_count("a.set-tile:not([hidden])", 2)
    harness.assert_text_present("2 of 18 sets")

    harness.select_by_label("#sets-sort", "Completion")

    # Still filtered, and the box still holds what was typed. Only fdn is
    # owned, so the other Foundations set is not in this sort's population —
    # the denominator moved because the population did, not because the filter
    # was reset.
    harness.assert_element_count("a.set-tile:not([hidden])", 1)
    harness.assert_visible("a.set-tile[href='/sets/fdn']")
    harness.assert_text_present("1 of 9 sets")

    # And the box is still live against the grid that is on the page now.
    harness.fill_by_placeholder(FILTER, "zzzz")
    harness.assert_element_count("a.set-tile:not([hidden])", 0)
    harness.assert_visible("#sets-no-match")

    # Clearing gives back everything this sort has to show, not everything the
    # page started with.
    harness.fill_by_placeholder(FILTER, "")
    harness.assert_element_count("a.set-tile:not([hidden])", 9)
    harness.assert_text_present("9 sets")
    harness.screenshot("final_state")
