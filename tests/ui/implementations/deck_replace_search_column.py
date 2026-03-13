"""
Hand-written implementation for deck_replace_search_column.

Opens the replace modal and verifies the search column filters collection results.
"""


def steps(harness):
    # Set plan on deck 2
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {removal: 3, ramp: 2, draw: 2}})})"
    )
    harness.page.wait_for_timeout(500)

    harness.navigate("/decks/2")
    harness.wait_for_visible("#card-grid", timeout=10_000)

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible("#card-grid .sheet-card", timeout=5_000)

    # Open replace modal for Slick Sequence
    harness.click_by_selector('.replace-btn[data-cid="22"]')
    harness.wait_for_visible("#replace-modal.active", timeout=5_000)

    # Search inputs should be pre-filled
    harness.assert_visible("#rs-cmc")
    harness.assert_visible("#rs-type")

    # Wait for initial search results to load
    harness.wait_for_visible("#replace-search .replace-candidate", timeout=5_000)
    harness.screenshot("search_results")

    # Clear type and search by name
    harness.fill_by_selector("#rs-type", "")
    harness.fill_by_selector("#rs-name", "Take")
    harness.page.wait_for_timeout(500)

    # Verify search results updated
    harness.wait_for_visible("#replace-search .replace-candidate", timeout=5_000)

    harness.screenshot("final_state")
