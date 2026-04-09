"""
Hand-written implementation for collection_search_debounced.

Types a card name into the search input, verifies the collection re-fetches
to show only matching cards, then clears the search to restore the full view.
"""


def steps(harness):
    # Navigate to Collection page and wait for table to load
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Type a search term using Scryfall syntax (debounced server fetch after 300ms)
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Scrawling")
    harness.wait_for_text("Scrawling Crawler")
    harness.screenshot("search_filtered")

    # Clear the search to restore full view
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "")
    harness.wait_for_text("43")

    harness.screenshot("final_state")
