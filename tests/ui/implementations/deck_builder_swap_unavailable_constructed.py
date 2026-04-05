"""
Hand-written implementation for deck_builder_swap_unavailable_constructed.

Verifies swap button does not appear on constructed decks but does
appear on idea decks.
"""


def steps(harness):
    # Create an idea deck with expected cards via API
    deck_id = harness.page.evaluate("""async () => {
        const res = await fetch('/api/decks', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Swap Vis Test', format: 'jumpstart', state: 'idea'})
        });
        const deck = await res.json();
        const colRes = await fetch('/api/collection?limit=50');
        const cards = await colRes.json();
        if (cards.length > 0) {
            await fetch('/api/decks/' + deck.id + '/expected-cards/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({printing_ids: [cards[0].printing_id]})
            });
        }
        return deck.id;
    }""")

    # Navigate to constructed deck
    harness.navigate("/decks/1")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Verify no swap buttons exist on constructed deck
    harness.assert_hidden(".swap-btn")

    harness.screenshot("constructed_no_swap")

    # Navigate to idea deck
    harness.navigate("/decks/" + str(deck_id))

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Verify swap buttons exist on idea deck
    harness.assert_visible(".swap-btn")

    harness.screenshot("final_state")
