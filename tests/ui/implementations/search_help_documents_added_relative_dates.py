"""
Hand-written implementation for search_help_documents_added_relative_dates.

Verifies that the /search-help page documents the timezone-aware
behavior and accepted formats of the `added` keyword.
"""


def steps(harness):
    harness.navigate("/search-help")
    harness.wait_for_text("Date Added")

    # The new local-tz prose
    harness.assert_text_present("added:today")
    harness.assert_text_present("local timezone")
    # Partial ISO date support
    harness.assert_text_present("added:2024-03")
    # Relative shortcut documentation
    harness.assert_text_present("7d")
    harness.screenshot("final_state")
