"""
Hand-written implementation for sheets_foil_sheet_indicators.

Loads BLB play sheets and verifies foil indicators: foil-tag in headers,
foil-pill in variants table, and .foil class on card wrappers.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play render before asserting anything. The deep link loads
    # two products: loadProducts() auto-checks the first one (collector,
    # 6 sheets) and fires a sheet load for it, then setSelectedProduct()
    # switches to play and fires a second. Both paint .section-header, and
    # collector has foil sheets of its own, so a wait on the header alone can
    # be satisfied by the collector render that is about to be replaced.
    # #status is written last, so the count is what tells the two apart.
    # 5 s (as in the sibling sheets scenarios) because this is the page load,
    # not an interaction.
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Verify foil tags exist in section header meta (foil sheets)
    harness.assert_visible(".foil-tag")

    # Verify foil-pill styling in variants table
    harness.assert_visible(".variant-pill.foil-pill")

    # Expand the "Foil" sheet section to see foil card wrappers
    # Use Playwright locator for exact h2 text match (not "Foil Land")
    harness.page.locator(".section-header").filter(has_text="Foil").first.click()
    # Verify foil card wrappers are visible in the expanded section.
    # BLB play's foil sheet is 322 tiles, all built at load time and hidden
    # behind `.section-body { display: none }`; the click unhides the whole
    # subtree at once, so the first tile is painted only after the browser has
    # laid out all 322. On a busy runner that overruns 500 ms (de-ezg: 1 fail
    # in 3 identical runs). 5 s because this waits out a render the scenario
    # itself asked for — it is not a measurement, and the 500 ms interaction
    # budget below still covers every assertion.
    harness.wait_for_visible(".section.open .sheet-card-img-wrap.foil", timeout=5_000)

    # Verify card wrappers have the foil class
    harness.assert_visible(".sheet-card-img-wrap.foil")

    harness.screenshot("final_state")
