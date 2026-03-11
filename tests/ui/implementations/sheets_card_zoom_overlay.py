"""
Hand-written implementation for sheets_card_zoom_overlay.

Loads BLB play sheets, expands a section, clicks a card to open
the zoom overlay, then clicks the overlay to dismiss it.
"""


def steps(harness):
    # start_page: /sheets — auto-navigated by test runner.

    # Wait for the set input to be ready
    harness.wait_for_visible("#set-input:not([disabled])", timeout=10_000)

    # Select BLB set
    harness.fill_by_selector("#set-input", "Bloom")
    harness.wait_for_visible("#set-dropdown li", timeout=10_000)
    harness.click_by_selector("#set-dropdown li")

    # Wait for products to load
    harness.wait_for_visible("#product-radios label", timeout=10_000)

    # Select play product
    harness.click_by_text("play", exact=True)

    # Wait for sheet sections to render
    harness.wait_for_visible(".section-header", timeout=15_000)

    # Expand the "Common" section to reveal cards (exact match)
    harness.click_by_text("Common", exact=True)
    # Use .section.open selector to target cards in expanded section only.
    harness.wait_for_visible(".section.open .sheet-card", timeout=10_000)

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
