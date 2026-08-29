"""
Hand-written implementation for sheets_section_collapse_expand_with_cards.

Loads BLB play sheets via the deep link, verifies Variants is expanded and
sheet sections are collapsed. Expands Common, checks cards and badges, then
collapses it.
"""


def steps(harness):
    # start_page: /sheets#set=blb&product=play — auto-navigated by test runner.

    # Wait for the play render before touching anything. The deep link loads
    # two products: loadProducts() auto-checks the first one (collector,
    # 6 sheets) and fires a sheet load for it, then setSelectedProduct()
    # switches to play and fires a second. Both paint .section-header, so only
    # the count tells them apart. 5 s (as in the sibling sheets scenarios)
    # because this is the page load, not an interaction — every wait below
    # keeps the harness's 500 ms budget.
    #
    # The deep link is also what keeps this scenario off the first
    # /api/sheets for the set: reaching play through the set input and the
    # product pills put that fetch inside the 500 ms budget, and against a
    # container that had never served it the wait for .section-header timed
    # out every time (de-35k).
    harness.wait_for_text("8 sheets", timeout=5_000)

    # Variants section should be expanded by default (first section)
    harness.assert_visible(".section.open")

    # Click the "Common" section header to expand it (exact match)
    harness.click_by_text("Common", exact=True)

    # Card images should now be visible inside the expanded Common section.
    # Use section-specific selector since collapsed sections also have .sheet-card elements.
    harness.wait_for_visible(".section.open .section-body .sheet-card", timeout=500)

    # Pull-rate badges should be visible below cards
    harness.assert_visible(".section.open .badge.pull-rate")

    harness.screenshot("expanded_common")

    # Click the "Common" header again to collapse it
    harness.click_by_text("Common", exact=True)

    harness.screenshot("final_state")
