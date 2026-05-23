"""
Hand-written implementation for deck_detail_zone_tab_switching.

Navigates to deck 1, verifies mainboard is active, switches to sideboard
and commander zones, checking card content at each step.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # The deck name and the zone-count badges render in separate async
    # passes, so wait for "(8)" with a timeout rather than asserting
    # immediately. Under runner load there's a measurable gap between
    # "Bolt Tribal" appearing and "(8)" landing in the DOM.
    harness.wait_for_text("Bolt Tribal")
    harness.wait_for_text("(8)")

    # Wait for grid to render (default view for small decks)
    harness.wait_for_visible(".grid-card")

    # Switch to Sideboard tab (filters grid view)
    harness.click_by_text("Sideboard")

    # Verify sideboard cards are shown in grid
    harness.wait_for_visible(".grid-card")
    harness.wait_for_text("(3)")

    # Switch to Commander tab
    harness.click_by_text("Commander")

    # Verify empty zone message
    harness.wait_for_text("No cards in this zone")
    harness.wait_for_text("(0)")

    harness.screenshot("final_state")
