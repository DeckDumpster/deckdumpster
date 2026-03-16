"""
Hand-written implementation for deck_detail_zone_tab_switching.

Navigates to deck 1, verifies mainboard is active, switches to sideboard
and commander zones, checking card content at each step.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for the deck to load
    harness.wait_for_text("Bolt Tribal")

    # Verify mainboard tab shows count
    harness.assert_text_present("(8)")

    # Verify mainboard has cards (grid view is default for small decks)
    harness.assert_text_present("Beast-Kin Ranger")

    # Switch to Sideboard tab (filters grid view)
    harness.click_by_text("Sideboard")

    # Verify sideboard cards are shown in grid
    harness.wait_for_text("Condemn")
    harness.assert_text_present("(3)")

    # Switch to Commander tab
    harness.click_by_text("Commander")

    # Verify empty zone message
    harness.wait_for_text("No cards in this zone")
    harness.assert_text_present("(0)")

    harness.screenshot("final_state")
