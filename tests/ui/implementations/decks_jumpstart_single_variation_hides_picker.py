"""
Hand-written implementation for decks_jumpstart_single_variation_hides_picker.

Picks Foundations "Goblins" — a single-decklist Jumpstart-type theme with
no sibling variations. Verifies the chip row stays hidden (nothing to
choose), the preview still renders, and Import succeeds.
"""


def steps(harness):
    # Open the modal and switch to the Jumpstart tab.
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=1000)
    harness.click_by_selector('.mode-tab[data-mode="jumpstart"]')
    harness.wait_for_visible("#mode-jumpstart.active", timeout=1000)
    # Set dropdown — pick Foundations (FDN has 10 single-variant Jumpstart decks).
    # <option> nodes are 'hidden' until the select is opened — wait_for_attached.
    harness.wait_for_attached(
        '#f-js-set option[value="fdn"]', timeout=3000)
    harness.select_by_label("#f-js-set", "Foundations — 10 decks")
    # Theme dropdown — pick "Goblins", no "(N variants)" suffix.
    harness.wait_for_attached(
        '#f-js-theme option[value="Goblins"]', timeout=3000)
    harness.select_by_label("#f-js-theme", "Goblins")
    # The variation chip wrapper stays hidden — nothing to choose among.
    harness.assert_hidden("#js-variation-group")
    # Preview still appears with card count.
    harness.wait_for_visible("#jumpstart-preview", timeout=1000)
    harness.assert_text_present("Will import")
    harness.assert_text_present("Goblins")
    # Import succeeds; deck name is "Goblins (Foundations)".
    # NOTE: target the button by ID — the preview text also contains "Import".
    harness.click_by_selector("#modal-save-btn")
    harness.wait_for_visible("#deck-builder-root h2", timeout=10000)
    harness.assert_text_present("Goblins (Foundations)")
    harness.screenshot("final_state")
