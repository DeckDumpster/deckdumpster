"""
Hand-written implementation for collection_search_autocomplete_added_value_shortcuts.

Types "added:" and verifies the autocomplete dropdown lists the
relative-date shortcuts ("today", "yesterday", "7d", "30d") served by
the new /api/search-suggest endpoint.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible("#search-input")

    # Colon triggers the dynamic value branch — an async fetch to
    # /api/search-suggest?key=added populates the dropdown.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "added:")

    harness.wait_for_visible("#ac-dropdown")
    # Wait for the async fetch to land — gating on a literal value.
    harness.wait_for_text("today")
    harness.assert_text_present("yesterday")
    harness.assert_text_present("7d")
    harness.assert_text_present("30d")
    harness.screenshot("final_state")
