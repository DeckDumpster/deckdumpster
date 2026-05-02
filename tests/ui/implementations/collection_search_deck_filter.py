"""
Hand-written implementation for collection_search_deck_filter.

Searches for cards in a specific deck using Scryfall syntax.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15000)

    # Search for cards in the Bolt Tribal deck
    harness.fill_by_placeholder(
        "Search (e.g. t:creature c:r mv>=3)",
        'deck:"Bolt Tribal"',
    )

    # Wait for filtered results (11 cards in Bolt Tribal)
    harness.wait_for_text("11 cards")

    # Verify a known card from the deck appears
    harness.wait_for_text("Beast-Kin Ranger")
    harness.screenshot("final_state")
