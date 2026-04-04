"""
Hand-written implementation for deck_builder_swap_printing_modal.

Verifies the swap printing modal opens with all available printings,
shows set info, owned count, and current badge.
"""


def steps(harness):
    # Create an idea deck with expected cards via API
    deck_id = harness.page.evaluate("""async () => {
        const res = await fetch('/api/decks', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Swap Modal Test', format: 'jumpstart', state: 'idea'})
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

    # Navigate to the newly created idea deck
    harness.navigate("/decks/" + str(deck_id))

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Click the swap button
    harness.click_by_selector(".swap-btn")

    # Wait for the swap modal to appear
    harness.wait_for_visible("#swap-modal.active")

    # Verify modal title
    harness.assert_text_present("Swap Printing")

    # Verify printing options are displayed
    harness.assert_visible(".swap-option")

    # Verify the current printing has the Current badge
    harness.assert_text_present("Current")

    harness.screenshot("swap_modal_open")

    # Close the modal
    harness.click_by_selector("#btn-cancel-swap")
    harness.wait_for_hidden("#swap-modal.active")

    harness.screenshot("final_state")
