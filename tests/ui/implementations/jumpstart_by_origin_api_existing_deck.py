"""
Hand-written implementation for jumpstart_by_origin_api_existing_deck.

Creates a precon deck with Jumpstart origin metadata via the Decks UI,
verifies origin info on the detail page, then navigates to decks list
to confirm the deck persists with correct metadata.
"""


def steps(harness):
    # start_page is /decks (auto-navigated by harness)
    harness.wait_for_text("New Deck", timeout=500)

    # Open deck creation modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=500)

    # Fill deck name
    harness.fill_by_placeholder("My Commander Deck", "Elves JMP")

    # Check "Preconstructed deck" to reveal origin fields
    harness.click_by_selector("#f-precon")
    harness.wait_for_visible("#precon-fields")

    # Select Jumpstart set and fill theme
    harness.select_by_label("#f-origin-set", "Jumpstart (JMP)")
    harness.fill_by_selector("#f-origin-theme", "Elves")

    # Save — auto-navigates to deck detail page
    harness.click_by_text("Save")
    harness.wait_for_text("Elves JMP", timeout=500)

    # Verify origin metadata on detail page
    harness.assert_text_present("Preconstructed")
    harness.assert_text_present("JMP")
    harness.assert_text_present("Elves")

    # Navigate back to deck list to confirm persistence
    harness.navigate("/decks")
    harness.wait_for_text("Elves JMP", timeout=500)
    harness.assert_text_present("Elves JMP")

    harness.screenshot("final_state")
