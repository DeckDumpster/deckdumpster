"""
Hand-written implementation for collection_search_clear_button_appears_after_url_restore.

Loads the collection page with a query already in the URL and verifies the
clear (×) button is visible without any user typing — the programmatic
value-set path in restoreFiltersFromURL() must call updateSearchClearVisibility().
"""


def steps(harness):
    # Open a shareable link with the search query already in the URL.
    harness.navigate("/collection?q=Scrawling")

    # Wait for the URL-driven filtered results to render.
    harness.wait_for_text("Scrawling Crawler")

    # The × button must already be visible — no typing happened.
    harness.assert_visible("#search-clear")
    harness.screenshot("clear_button_visible_from_url")

    # Click the × to clear the URL-driven query.
    harness.click_by_selector("#search-clear")

    # Full collection comes back and the × hides.
    harness.wait_for_text("45 cards")
    harness.assert_hidden("#search-clear")

    harness.screenshot("final_state")
