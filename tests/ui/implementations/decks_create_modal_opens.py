"""
Hand-written implementation for decks_create_modal_opens.

Opens the New Deck modal and verifies the three-tab picker (Blank /
Preconstructed / Jumpstart) is wired up: Blank mode shows the core
form fields, switching to Preconstructed swaps in the set picker.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for page to load
    harness.wait_for_text("New Deck")

    # Click "New Deck" button
    harness.click_by_text("New Deck")

    # Wait for modal to appear
    harness.wait_for_visible("#deck-modal.active")

    # Three tabs are present; Blank is active by default.
    harness.assert_visible('.mode-tab[data-mode="blank"].active')
    harness.assert_visible('.mode-tab[data-mode="precon"]')
    harness.assert_visible('.mode-tab[data-mode="jumpstart"]')

    # Blank mode: core form fields are visible.
    harness.assert_visible("#f-name")
    harness.assert_visible("#f-format")
    harness.assert_visible("#f-description")

    # Shared fields are visible under every mode.
    harness.assert_visible("#f-sleeve")
    harness.assert_visible("#f-deckbox")
    harness.assert_visible("#f-location")
    harness.assert_visible("#f-deck-state")

    # Primary action button starts as "Create"; Cancel button is present.
    harness.assert_text_present("Create")
    harness.assert_text_present("Cancel")

    # Switch to Preconstructed — the set picker appears, the blank-mode
    # form fields go away, and the save button flips to "Import".
    harness.click_by_selector('.mode-tab[data-mode="precon"]')
    harness.wait_for_visible("#mode-precon.active")
    harness.assert_visible("#f-precon-set")
    harness.assert_visible("#f-precon-deck")
    harness.assert_hidden("#mode-blank")
    harness.assert_text_present("Import")

    harness.screenshot("final_state")
