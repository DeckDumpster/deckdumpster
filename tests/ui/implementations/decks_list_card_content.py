"""
Hand-written implementation for decks_list_card_content.

Verifies that each deck card in the grid displays name, format badge,
card count, and description text.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for deck grid to load
    harness.wait_for_text("Bolt Tribal")

    # Verify Bolt Tribal card content
    harness.assert_text_present("Bolt Tribal")
    harness.assert_text_present("modern")
    harness.assert_text_present("11 cards")
    harness.assert_text_present("Burn deck")

    # Verify Eldrazi Ramp card content
    harness.assert_text_present("Eldrazi Ramp")
    harness.assert_text_present("commander")
    harness.assert_text_present("6 cards")
    harness.assert_text_present("Big mana Eldrazi")

    harness.screenshot("final_state")
