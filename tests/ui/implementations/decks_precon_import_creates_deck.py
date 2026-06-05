"""
Hand-written implementation for decks_precon_import_creates_deck.

Imports the SPM "Red Deck" Welcome Deck via the Preconstructed tab.
Verifies the live preview text, then clicks Import and confirms the
browser lands on the new deck's detail page with the expected name.
"""


def steps(harness):
    # Open the modal and switch to the Preconstructed tab.
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=1000)
    harness.click_by_selector('.mode-tab[data-mode="precon"]')
    harness.wait_for_visible("#mode-precon.active", timeout=1000)
    # Set dropdown is populated from GET /api/precons/sets?kind=precon.
    # <option> nodes are 'hidden' until the select is opened — wait_for_attached.
    harness.wait_for_attached(
        '#f-precon-set option[value="spm"]', timeout=3000)
    harness.select_by_label("#f-precon-set", "Marvel's Spider-Man — 5 decks")
    # Deck dropdown is populated after a set is chosen.
    harness.wait_for_attached(
        '#f-precon-deck option[value="Red Deck"]', timeout=3000)
    harness.select_by_label("#f-precon-deck", "Red Deck — Welcome Deck")
    # Live preview line appears with card count + deck name.
    harness.wait_for_visible("#precon-preview", timeout=1000)
    harness.assert_text_present("Will import")
    harness.assert_text_present("30")
    harness.assert_text_present("Red Deck")
    # Import — server creates the deck and the client navigates to /decks/:id.
    # NOTE: target the button by ID, not text — the live preview ("Will import...")
    # also contains the substring "Import" and would match first.
    harness.click_by_selector("#modal-save-btn")
    # Wait for the standalone deck-builder page to finish hydrating, then
    # confirm the auto-generated deck name appears in the H2.
    harness.wait_for_visible("#deck-builder-root h2", timeout=10000)
    harness.assert_text_present("Red Deck (Marvel's Spider-Man)")
    harness.screenshot("final_state")
