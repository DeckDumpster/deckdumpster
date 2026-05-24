"""
Hand-written implementation for collection_search_autocomplete_added_operators.

Types the bare keyword "added" and verifies the autocomplete dropdown
lists the comparison operators the search compiler accepts for date
keywords.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible("#search-input")

    # Bare keyword (no operator) — should trigger operator suggestions.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "added")

    harness.wait_for_visible("#ac-dropdown")
    # Each operator the date keyword accepts should appear in the dropdown.
    harness.assert_text_present("added:")
    harness.assert_text_present("added>=")
    harness.assert_text_present("added<=")
    harness.assert_text_present("added>")
    harness.screenshot("final_state")
