"""
Hand-written implementation for edit_order_replace_card.

Opens the search overlay in replace mode, searches for a card, selects
a result, and verifies the original card is replaced.
"""


def steps(harness):
    # start_page: /edit-order?id=1 — auto-navigated by test runner.
    harness.wait_for_visible(".card-row", timeout=10_000)
    # Note the original card name in the last row.
    harness.assert_text_present("Witness Protection")
    # Click the replace button on the last card row.
    # The replace buttons use the swap icon (title="Replace card").
    # Use click_by_selector to get the last replace button.
    # There are multiple .btn-icon[title='Replace card'] — click the last one.
    replace_buttons = harness.page.locator(".btn-icon[title='Replace card']")
    replace_buttons.last.click()
    harness.page.wait_for_timeout(500)
    # Wait for the search overlay to open.
    harness.wait_for_visible("#search-overlay.active", timeout=5_000)
    # Type a search query (must be a card in the fixture DB) and wait for debounce + API
    harness.fill_by_selector("#search-input", "Beast-Kin Ranger")
    harness.page.wait_for_timeout(1000)
    # Wait for search results.
    harness.wait_for_visible(".search-candidate", timeout=15_000)
    # Click the first search result.
    harness.click_by_selector(".search-candidate")
    # Overlay closes and card list refreshes.
    harness.wait_for_hidden("#search-overlay.active", timeout=5_000)
    harness.wait_for_visible(".card-row", timeout=10_000)
    # Verify original card is gone.
    harness.assert_text_absent("Witness Protection")
    harness.screenshot("final_state")
