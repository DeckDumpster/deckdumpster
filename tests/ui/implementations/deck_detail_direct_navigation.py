"""
Hand-written implementation for deck_detail_direct_navigation.

Navigates directly to /decks/1 and verifies the standalone deck detail
page renders with deck name, metadata, zone tabs, and card table.
"""


def steps(harness):
    # Navigate directly to deck detail page
    harness.navigate("/decks/1")

    # Wait for the deck name to appear
    harness.wait_for_text("Bolt Tribal")

    # Verify deck name is displayed
    harness.assert_text_present("Bolt Tribal")

    # Verify metadata is shown (format)
    harness.assert_text_present("modern")

    # Verify zone tabs are visible
    harness.assert_text_present("Mainboard")
    harness.assert_text_present("Sideboard")
    harness.assert_text_present("Commander")

    # Verify card table has content (a card from the deck)
    harness.assert_text_present("Beast-Kin Ranger")

    # Verify action buttons are present
    harness.assert_text_present("Edit")
    harness.assert_text_present("Add Cards")
    harness.assert_text_present("Delete Deck")

    harness.screenshot("final_state")
