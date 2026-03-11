"""
Hand-written implementation for recent_card_status_borders.

Verifies DONE and ERROR cards have correct CSS classes and error indicators.
"""


def steps(harness):
    # Wait for grid and cards to load (async via loadRecent)
    harness.wait_for_visible("#grid")
    harness.wait_for_visible(".img-card")

    # Switch to grid view — default is table mode where error-icon is
    # hidden via display:none.  Grid view shows all overlays.
    harness.click_by_selector("#view-toggle")
    harness.wait_for_visible(".img-card")

    # Verify DONE cards exist with green border class
    harness.assert_visible(".img-card.done")
    harness.assert_element_count(".img-card.done", 2)

    # Verify ERROR cards exist with red border class
    harness.assert_visible(".img-card.error")
    harness.assert_element_count(".img-card.error", 2)

    # Verify error icon is present on error cards
    harness.assert_visible(".img-card.error .error-icon")

    harness.screenshot("final_state")
