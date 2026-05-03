"""
Hand-written implementation for collection_shared_card_list.

Verifies that a shared card list URL renders specific cards in grid view.
"""


def steps(harness):
    # start_page from hints navigates to /collection?cards=fdn:188,otj:196&view=grid

    # Wait for the grid to render with card images
    harness.wait_for_visible(".sheet-card", timeout=10_000)

    # Verify status bar shows count (1 owned + 1 unowned = 1 owned card)
    harness.wait_for_text("1 card", timeout=10_000)

    # Verify both cards are rendered
    harness.assert_element_count(".sheet-card", 2)

    # Verify unowned card has the dimmed style
    harness.assert_visible(".sheet-card.unowned")

    harness.screenshot("final_state")
