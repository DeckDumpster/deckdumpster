"""
Hand-written implementation for deck_edit_change_commander.

Sets Bonny Pall as commander via API, then uses the Edit modal to change
it to Phlage, and verifies the preview updates.
"""


def steps(harness):
    # Set Bonny Pall as commander via API (prerequisite)
    harness.page.evaluate("""async () => {
        const res = await fetch('/api/decks/2/cards');
        const cards = await res.json();
        const bonny = cards.find(c => c.name === 'Bonny Pall, Clearcutter');
        await fetch('/api/decks/2', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'Eldrazi Ramp',
                commander_oracle_id: bonny.oracle_id,
                commander_printing_id: bonny.printing_id
            })
        });
    }""")

    # Navigate to deck 2
    harness.navigate("/decks/2")
    harness.wait_for_text("Bonny Pall, Clearcutter")

    # Click Edit button
    harness.click_by_text("Edit")
    harness.wait_for_visible("#deck-modal.active")

    # Change commander to Phlage
    harness.select_by_label("#f-commander", "Phlage, Titan of Fire's Fury")

    # Save
    harness.click_by_selector("#btn-save-deck")
    harness.wait_for_hidden("#deck-modal.active")

    # Verify the new commander name appears in the preview
    harness.wait_for_text("Phlage, Titan of Fire's Fury")
    harness.assert_text_present("Phlage, Titan of Fire's Fury")

    harness.screenshot("final_state")
