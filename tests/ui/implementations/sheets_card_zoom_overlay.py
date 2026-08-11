"""
Hand-written implementation for sheets_card_zoom_overlay.

Loads BLB play sheets via the deep link, expands a section, clicks a card
to open the zoom overlay, then clicks the overlay to dismiss it.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play sheets to finish rendering. "8 sheets" rather than
    # .section-header because the deep link loads two products: loadProducts()
    # auto-checks the first one (collector, 6 sheets) and fires a sheet load
    # for it, then setSelectedProduct() switches to play and fires a second.
    # Both paint .section-header, so only the count tells them apart.
    # 5 s (as in sheets_deep_link_url_hash) because this is the page load, not
    # an interaction — every wait below keeps the harness's 500 ms budget.
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Expand the "Common" section to reveal cards (exact match)
    harness.click_by_text("Common", exact=True)
    # Use .section.open selector to target cards in expanded section only.
    harness.wait_for_visible(".section.open .sheet-card", timeout=500)

    # Click the first visible card to open zoom overlay
    harness.click_by_selector(".section.open .sheet-card")

    # Verify the zoom overlay is active
    harness.wait_for_visible("#zoom-overlay.active")

    harness.screenshot("zoom_open")

    # Click the overlay to dismiss it
    harness.click_by_selector("#zoom-overlay")

    # Verify the overlay is hidden
    harness.wait_for_hidden("#zoom-overlay.active")

    harness.screenshot("final_state")
