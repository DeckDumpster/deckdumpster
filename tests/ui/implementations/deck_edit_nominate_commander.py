"""
Hand-written implementation for deck_edit_nominate_commander.

Opens Edit on a commander deck with no commander set, selects a legendary
creature from the Commander dropdown, saves, and verifies the preview updates.
"""


def steps(harness):
    # Ensure deck 2 has no commander set
    harness.page.evaluate("""async () => {
        await fetch('/api/decks/2', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Eldrazi Ramp', commander_oracle_id: null, commander_printing_id: null})
        });
    }""")

    # Navigate to deck 2 (Eldrazi Ramp, commander format)
    harness.navigate("/decks/2")
    harness.wait_for_text("Eldrazi Ramp")

    # Click Edit button
    harness.click_by_text("Edit")
    harness.wait_for_visible("#deck-modal.active")

    # Select "Bonny Pall, Clearcutter" from the Commander dropdown
    harness.select_by_label("#f-commander", "Bonny Pall, Clearcutter")

    # Save the deck
    harness.click_by_selector("#btn-save-deck")
    harness.wait_for_hidden("#deck-modal.active")

    # Verify the commander name appears in the preview panel
    harness.wait_for_text("Bonny Pall, Clearcutter")
    harness.assert_text_present("Bonny Pall, Clearcutter")

    harness.screenshot("final_state")
