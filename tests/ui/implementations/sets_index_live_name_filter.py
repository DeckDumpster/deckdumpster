"""
Hand-written implementation for sets_index_live_name_filter.

Walks the client-side filter: name match, code match, no match, and cleared.

Filtered-out tiles stay in the DOM with the `hidden` attribute, and
assert_text_absent counts attached nodes regardless of visibility — so
everything here is asserted with `:not([hidden])` counts and assert_hidden.
"""

FILTER = "Filter by set name or code"


def steps(harness):
    harness.assert_element_count("a.set-tile:not([hidden])", 18)

    # A name match. Two sets are named Foundations; both survive.
    harness.fill_by_placeholder(FILTER, "foundations")
    harness.assert_element_count("a.set-tile:not([hidden])", 2)
    harness.assert_text_present("2 of 18 sets")
    harness.assert_visible("a.set-tile[href='/sets/fdn']")
    harness.assert_visible("a.set-tile[href='/sets/j25']")
    # A block that lost every set is hidden, not left standing and empty.
    harness.assert_hidden("section.set-group[data-set-type='expansion']")
    # The surviving blocks recount: core holds 1 of its 2 sets now.
    harness.assert_element_count(
        "section.set-group[data-set-type='core']:not([hidden])", 1
    )

    # A code match — 'fin' is nobody's name here, only Final Fantasy's code.
    harness.fill_by_placeholder(FILTER, "fin")
    harness.assert_element_count("a.set-tile:not([hidden])", 1)
    harness.assert_visible("a.set-tile[href='/sets/fin']")

    # No match is said out loud rather than shown as a blank page.
    harness.fill_by_placeholder(FILTER, "zzzz")
    harness.assert_element_count("a.set-tile:not([hidden])", 0)
    harness.assert_visible("#sets-no-match")
    harness.assert_text_present("No set matches that filter.")

    # Clearing restores everything.
    harness.fill_by_placeholder(FILTER, "")
    harness.assert_element_count("a.set-tile:not([hidden])", 18)
    harness.assert_element_count("section.set-group:not([hidden])", 5)
    harness.assert_hidden("#sets-no-match")
    harness.screenshot("final_state")
