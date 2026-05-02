"""
Hand-written implementation for collection_search_status_default.

Verifies default status filter shows owned+ordered, then explicit
status:ordered narrows results.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Default: should show owned + ordered cards (43 entries, 45 cards)
    harness.wait_for_text("45 cards")
    harness.screenshot("default_view")

    # Search for status:ordered only
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "status:ordered")
    harness.wait_for_text("5 cards")
    harness.screenshot("final_state")
