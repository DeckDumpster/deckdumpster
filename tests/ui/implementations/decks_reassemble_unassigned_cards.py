"""
Hand-written implementation for decks_reassemble_unassigned_cards.

Opens Bolt Tribal (standalone deck detail page at /decks/1), imports an
expected list with one unassigned card (Cathar Commando), then clicks
the reassemble button to move it into the deck. Verifies the card
moves from Missing to Present.
"""


def steps(harness):
    # Click "Bolt Tribal" deck link — navigates to /decks/1 standalone page.
    harness.click_by_text("Bolt Tribal")
    # Wait for the standalone deck detail page to load.
    harness.wait_for_visible("#btn-import-expected", timeout=10_000)
    # Import expected list with only Cathar Commando (unassigned in collection).
    harness.click_by_text("Import Expected List")
    harness.wait_for_visible("#expected-modal.active", timeout=5_000)
    harness.fill_by_selector("#f-expected-list", "1 Cathar Commando (FDN) 139")
    harness.click_by_selector("#expected-modal button")
    harness.wait_for_hidden("#expected-modal.active", timeout=5_000)
    harness.wait_for_visible("#completeness-section", timeout=5_000)
    # Verify Cathar Commando is missing with Unassigned tag.
    harness.assert_text_present("Missing")
    harness.assert_text_present("Cathar Commando")
    harness.assert_text_present("Unassigned")
    # Click the "Reassemble 1 Unassigned Card" button.
    harness.click_by_text("Reassemble 1 Unassigned Card")
    # Wait for completeness to refresh — Cathar Commando should now be Present.
    harness.wait_for_text("Present", timeout=5_000)
    harness.assert_text_present("Cathar Commando")
    harness.assert_text_absent("Unassigned")
    harness.screenshot("final_state")
