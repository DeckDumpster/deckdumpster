"""
Hand-written implementation for recent_accordion_open_close.

Opens and closes the accordion panel on a DONE image card.
"""


def steps(harness):
    # Wait for grid and DONE cards to load (async via loadRecent)
    harness.wait_for_visible("#grid")
    harness.wait_for_visible(".img-card.done")

    # Click the first DONE card to open accordion
    harness.click_by_selector(".img-card.done")

    # Verify accordion opens (panel id is "accordion-panel", class "open" is toggled)
    harness.wait_for_visible("#accordion-panel.open")
    harness.assert_visible(".img-card.selected")
    harness.screenshot("accordion_open")

    # Click the same card again to close accordion
    harness.click_by_selector(".img-card.selected")

    # Verify accordion closes
    harness.wait_for_hidden("#accordion-panel.open")

    harness.screenshot("final_state")
