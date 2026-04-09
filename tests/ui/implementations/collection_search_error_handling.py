"""
Hand-written implementation for collection_search_error_handling.

Types an invalid query and verifies error message appears, then
clears to dismiss the error.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible("#search-input")

    # Type an invalid query with unclosed parenthesis
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "(unclosed")

    # Error message should appear
    harness.wait_for_text("Missing closing parenthesis")
    harness.screenshot("error_shown")

    # Clear the search to dismiss error
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "")

    # Error should be gone, cards should reload
    harness.wait_for_visible(".collection-table", timeout=15000)
    harness.screenshot("final_state")
