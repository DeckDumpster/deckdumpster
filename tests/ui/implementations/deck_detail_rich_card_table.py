"""
Hand-written implementation for deck_detail_rich_card_table.

Navigates to a deck detail page, switches to list view, and verifies the
type-grouped list renders card names with mana symbols.
"""


def steps(harness):
    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for deck to load (default is grid view for small decks)
    harness.wait_for_text("Beast-Kin Ranger")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")

    # Verify type group headers render
    harness.assert_text_present("Creatures")

    # Verify card names are visible in list view
    harness.assert_visible("#type-groups .card-row")

    # Verify mana symbols render (mana-font ms icon)
    harness.assert_visible("#type-groups .mana-icons .ms")

    # Verify card links exist
    harness.assert_visible("#type-groups .card-name a")

    harness.screenshot("final_state")
