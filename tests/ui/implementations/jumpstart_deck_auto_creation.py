"""
Hand-written implementation for jumpstart_deck_auto_creation.

Creates a precon deck with Jumpstart origin metadata via the Decks UI,
verifies the origin info on the detail page, then navigates back to the
deck list to confirm the deck persists.
"""


def steps(harness):
    # start_page is /decks (auto-navigated by harness)
    harness.wait_for_text("New Deck", timeout=5_000)

    # Open deck creation modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=5_000)

    # Fill deck name
    harness.fill_by_placeholder("My Commander Deck", "Goblins JMP Test")

    # Check "Preconstructed deck" to reveal origin fields
    harness.click_by_selector("#f-precon")
    harness.wait_for_visible("#precon-fields")

    # Select Jumpstart set and fill theme
    harness.select_by_label("#f-origin-set", "Jumpstart (JMP)")
    harness.fill_by_selector("#f-origin-theme", "Goblins")

    # Save — auto-navigates to deck detail page
    harness.click_by_text("Save")
    harness.wait_for_text("Goblins JMP Test", timeout=10_000)

    # Verify origin metadata on detail page
    harness.assert_text_present("Preconstructed")
    harness.assert_text_present("JMP")
    harness.assert_text_present("Goblins")

    # Navigate back to deck list
    harness.navigate("/decks")
    harness.wait_for_text("Goblins JMP Test", timeout=5_000)

    # Verify the deck appears in the list
    harness.assert_text_present("Goblins JMP Test")

    harness.screenshot("final_state")
