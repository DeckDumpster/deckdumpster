"""
Hand-written implementation for deck_edit_clear_commander.

Sets Phlage as commander via API, then uses the Edit modal to clear it
by selecting "-- None --", and verifies the preview falls back to deck name.
"""


def steps(harness):
    # Set Phlage as commander via API (prerequisite)
    harness.page.evaluate("""async () => {
        const res = await fetch('/api/decks/2/cards');
        const cards = await res.json();
        const phlage = cards.find(c => c.name.includes('Phlage'));
        await fetch('/api/decks/2', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: 'Eldrazi Ramp',
                commander_oracle_id: phlage.oracle_id,
                commander_printing_id: phlage.printing_id
            })
        });
    }""")

    # Navigate to deck 2
    harness.navigate("/decks/2")
    harness.wait_for_text("Phlage")

    # Click Edit button
    harness.click_by_text("Edit")
    harness.wait_for_visible("#deck-modal.active")

    # Clear commander by selecting "-- None --"
    harness.select_by_label("#f-commander", "-- None --")

    # Save
    harness.click_by_selector("#btn-save-deck")
    harness.wait_for_hidden("#deck-modal.active")

    # After clearing, the preview should show the deck name as fallback
    harness.wait_for_text("Eldrazi Ramp")
    # The preview-name should show "Eldrazi Ramp" not a commander name
    harness.assert_visible("#preview-name")
    # Commander image should not be present
    harness.assert_hidden("#preview-img")

    harness.screenshot("final_state")
