"""
Hand-written implementation for collection_search_clear_button_visibility_toggle.

Verifies the × button is hidden when the input is empty, appears when the user
types, and hides again once the input is empty.
"""


def steps(harness):
    # Navigate to Collection page and wait for the table to render.
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Empty input → clear button hidden.
    harness.assert_hidden("#search-clear")
    harness.screenshot("initial_hidden")

    # Type a query → clear button becomes visible.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Scrawling")
    harness.wait_for_text("Scrawling Crawler")
    harness.assert_visible("#search-clear")
    harness.screenshot("with_query_visible")

    # Empty the input by filling with "" → clear button hides again.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "")
    harness.wait_for_text("45 cards")
    harness.assert_hidden("#search-clear")

    harness.screenshot("final_state")
