"""
Hand-written implementation for decks_jumpstart_variation_picker.

Picks J25 "Angels" (which has 2 sibling variations), clicks the
non-default variation chip, verifies the highlight moves and the
preview updates, then imports that variant.
"""


def steps(harness):
    # Open the modal and switch to the Jumpstart tab.
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=1000)
    harness.click_by_selector('.mode-tab[data-mode="jumpstart"]')
    harness.wait_for_visible("#mode-jumpstart.active", timeout=1000)
    # Set dropdown — pick Foundations Jumpstart (J25, has many multi-variant themes).
    # <option> nodes are 'hidden' until the select is opened — wait_for_attached.
    harness.wait_for_attached(
        '#f-js-set option[value="j25"]', timeout=3000)
    harness.select_by_label("#f-js-set", "Foundations Jumpstart — 121 decks")
    # Theme dropdown — pick Angels, which has 2 variations.
    harness.wait_for_attached(
        '#f-js-theme option[value="Angels"]', timeout=3000)
    harness.select_by_label("#f-js-theme", "Angels (2 variants)")
    # The variation chip row appears; the first chip (Angels (1)) is .checked.
    harness.wait_for_visible(
        '#f-js-variations label[data-name="Angels (1)"]', timeout=1000)
    harness.assert_visible(
        '#f-js-variations label[data-name="Angels (1)"].checked')
    # Click the second variation chip.
    harness.click_by_selector(
        '#f-js-variations label[data-name="Angels (2)"]')
    # The highlight moved.
    harness.assert_visible(
        '#f-js-variations label[data-name="Angels (2)"].checked')
    # Preview line now names the second variation.
    harness.wait_for_visible("#jumpstart-preview", timeout=1000)
    harness.assert_text_present("Angels (2)")
    # Import — navigates to /decks/:id with the auto-generated name.
    # NOTE: target the button by ID — the preview text also contains "Import".
    harness.click_by_selector("#modal-save-btn")
    harness.wait_for_visible("#deck-builder-root h2", timeout=10000)
    harness.assert_text_present("Angels (2) (Foundations Jumpstart)")
    harness.screenshot("final_state")
