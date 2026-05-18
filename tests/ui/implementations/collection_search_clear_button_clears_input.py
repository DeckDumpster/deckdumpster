"""
Hand-written implementation for collection_search_clear_button_clears_input.

Types a query, verifies the clear (×) button appears, clicks it, and confirms
the input empties, the button hides, and the full collection comes back.
"""


def steps(harness):
    # Navigate to Collection page and wait for the table to render.
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)

    # Clear button should be hidden when the input starts empty.
    harness.assert_hidden("#search-clear")

    # Type a query and wait for the filtered results.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Scrawling")
    harness.wait_for_text("Scrawling Crawler")

    # Clear button is now visible because the input has content.
    harness.assert_visible("#search-clear")
    harness.screenshot("clear_button_visible")

    # Click the × button to clear the search.
    harness.click_by_selector("#search-clear")

    # Full collection should be back and the × should be hidden again.
    harness.wait_for_text("45 cards")
    harness.assert_hidden("#search-clear")

    harness.screenshot("final_state")
