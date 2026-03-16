"""
Hand-written implementation for deck_detail_card_links_to_card_page.

Navigates to a deck detail page, clicks a grid card to open the modal,
then clicks the "Full page" link to navigate to the card detail page.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for grid to render (default view for small decks)
    harness.wait_for_visible(".grid-card")

    # Click on a grid card to open the modal
    harness.click_by_selector(".grid-card")

    # Wait for the card modal to appear
    harness.wait_for_visible(".card-modal-overlay.active")

    # Click the "Full page" link in the modal
    harness.click_by_text("Full page")

    # Wait for card detail page to load
    harness.wait_for_visible(".card-detail-layout")

    # Verify we're on the card detail page
    harness.assert_text_present("Beast-Kin Ranger")

    harness.screenshot("final_state")
