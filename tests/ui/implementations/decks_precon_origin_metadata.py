"""
Hand-written implementation for decks_precon_origin_metadata.

Creates a precon deck with Jumpstart origin metadata (set, theme,
variation), then verifies the metadata is displayed in the standalone
deck detail page (navigated to automatically after save).
"""


def steps(harness):
    # Click "New Deck" to open the creation modal.
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=5_000)
    # Fill in deck name.
    harness.fill_by_placeholder("My Commander Deck", "Goblins JMP")
    # Check the "Preconstructed deck" checkbox to reveal origin fields.
    harness.click_by_selector("#f-precon")
    harness.wait_for_visible("#precon-fields")
    # Select "Jumpstart (JMP)" from Origin Set dropdown.
    harness.select_by_label("#f-origin-set", "Jumpstart (JMP)")
    # Type "Goblins" in the Theme field.
    harness.fill_by_selector("#f-origin-theme", "Goblins")
    # Type "1" in the Variation field.
    harness.fill_by_selector("#f-origin-variation", "1")
    # Save the deck — saveDeck() auto-navigates to /decks/:id standalone page.
    harness.click_by_text("Save")
    # Wait for the standalone deck detail page to load (deck name appears).
    harness.wait_for_text("Goblins JMP", timeout=10_000)
    harness.assert_text_present("Preconstructed")
    harness.assert_text_present("JMP")
    harness.assert_text_present("Goblins")
    harness.screenshot("final_state")
