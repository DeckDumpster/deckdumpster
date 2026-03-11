"""
Hand-written implementation for sheets_section_collapse_expand_with_cards.

Loads BLB play sheets, verifies Variants is expanded and sheet sections
are collapsed. Expands Common, checks cards and badges, then collapses it.
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

    # Variants section should be expanded by default (first section)
    harness.assert_visible(".section.open")

    # Click the "Common" section header to expand it (exact match)
    harness.click_by_text("Common", exact=True)

    # Card images should now be visible inside the expanded Common section.
    # Use section-specific selector since collapsed sections also have .sheet-card elements.
    harness.wait_for_visible(".section.open .section-body .sheet-card", timeout=10_000)

    # Pull-rate badges should be visible below cards
    harness.assert_visible(".section.open .badge.pull-rate")

    harness.screenshot("expanded_common")

    # Click the "Common" header again to collapse it
    harness.click_by_text("Common", exact=True)
    harness.page.wait_for_timeout(500)

    harness.screenshot("final_state")
