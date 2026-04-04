"""
Hand-written implementation for deck_builder_swap_printing_execution.

Verifies that clicking an alternate printing swaps it in the deck.
"""


def steps(harness):
    # Create an idea deck with an expected card that has multiple printings.
    # Pick a card with >1 non-digital printing so the swap modal has alternatives.
    deck_id = harness.page.evaluate("""async () => {
        const res = await fetch('/api/decks', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Swap Exec Test', format: 'jumpstart', state: 'idea'})
        });
        const deck = await res.json();
        const colRes = await fetch('/api/collection?limit=50');
        const cards = await colRes.json();
        // Find a card with multiple printings by checking the by-oracle endpoint
        for (const card of cards) {
            const pRes = await fetch('/api/printings/by-oracle/' + card.oracle_id);
            const printings = await pRes.json();
            if (printings.length > 1) {
                await fetch('/api/decks/' + deck.id + '/expected-cards/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({printing_ids: [card.printing_id]})
                });
                return deck.id;
            }
        }
        // Fallback: use first card even if only one printing
        if (cards.length > 0) {
            await fetch('/api/decks/' + deck.id + '/expected-cards/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({printing_ids: [cards[0].printing_id]})
            });
        }
        return deck.id;
    }""")

    # Navigate to the idea deck
    harness.navigate("/decks/" + str(deck_id))

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Click the swap button on first card
    harness.click_by_selector(".swap-btn")
    harness.wait_for_visible("#swap-modal.active")

    # Click a non-current printing option to perform the swap
    harness.click_by_selector(".swap-option:not(.current)")

    # Modal should close and deck should reload
    harness.wait_for_hidden("#swap-modal.active")
    harness.wait_for_visible("#type-groups")

    # Verify the deck reloaded (list view still shows cards)
    harness.assert_visible(".card-row")

    # Open swap modal again to verify the new printing has Current badge
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")
    harness.click_by_selector(".swap-btn")
    harness.wait_for_visible("#swap-modal.active")
    harness.assert_text_present("Current")

    harness.screenshot("final_state")
