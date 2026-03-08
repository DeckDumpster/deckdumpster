"""
Hand-written implementation for deck_detail_card_links_to_card_page.

Navigates to a deck detail page, clicks a card name link, and verifies
it navigates to the card detail page.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for card table to load
    harness.wait_for_text("Beast-Kin Ranger")

    # Click the card name link (it's an <a> tag in the table)
    harness.click_by_text("Beast-Kin Ranger")

    # Wait for card detail page to load
    harness.wait_for_visible(".card-detail-layout")

    # Verify we're on the card detail page
    harness.assert_text_present("Beast-Kin Ranger")

    harness.screenshot("final_state")
