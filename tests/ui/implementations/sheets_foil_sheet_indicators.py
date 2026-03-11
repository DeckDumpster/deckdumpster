"""
Hand-written implementation for sheets_foil_sheet_indicators.

Loads BLB play sheets and verifies foil indicators: foil-tag in headers,
foil-pill in variants table, and .foil class on card wrappers.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for sections to render
    harness.wait_for_visible(".section-header", timeout=15_000)

    # Verify foil tags exist in section header meta (foil sheets)
    harness.assert_visible(".foil-tag")

    # Verify foil-pill styling in variants table
    harness.assert_visible(".variant-pill.foil-pill")

    # Expand the "Foil" sheet section to see foil card wrappers
    # Use Playwright locator for exact h2 text match (not "Foil Land")
    harness.page.locator(".section-header").filter(has_text="Foil").first.click()
    harness.page.wait_for_timeout(500)
    # Verify foil card wrappers are visible in the expanded section
    harness.wait_for_visible(".section.open .sheet-card-img-wrap.foil", timeout=10_000)

    # Verify card wrappers have the foil class
    harness.assert_visible(".sheet-card-img-wrap.foil")

    harness.screenshot("final_state")
