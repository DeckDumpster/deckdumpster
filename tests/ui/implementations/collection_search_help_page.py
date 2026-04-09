"""
Hand-written implementation for collection_search_help_page.

Navigates to the search help page and verifies key sections exist.
"""


def steps(harness):
    harness.navigate("/search-help")

    # Verify main section headings are present
    harness.wait_for_text("Search Syntax")
    harness.assert_text_present("Standard Scryfall Keywords")
    harness.assert_text_present("Collection-Specific Extensions")
    harness.assert_text_present("Example Queries")

    # Verify collection extension keywords are documented
    harness.assert_text_present("status:")
    harness.assert_text_present("deck:")
    harness.assert_text_present("binder:")
    harness.assert_text_present("is:unassigned")

    harness.screenshot("final_state")
