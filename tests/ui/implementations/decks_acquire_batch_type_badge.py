"""
Hand-written implementation for decks_acquire_batch_type_badge.

Creates a Jumpstart deck, acquires it, then navigates to /batches to verify
the batch entry shows the "Deck" label rather than the raw "deck_acquire" string.
"""

from tests.ui.budget import INTERACTION_BUDGET_MS, ROUND_TRIP_BUDGET_MS


def steps(harness):
    # Open the modal and switch to the Jumpstart tab.
    harness.navigate("/decks")
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=ROUND_TRIP_BUDGET_MS)
    harness.click_by_selector('.mode-tab[data-mode="jumpstart"]')
    harness.wait_for_visible("#mode-jumpstart.active", timeout=INTERACTION_BUDGET_MS)

    # Select Foundations Jumpstart and Angels theme; import with default variation.
    harness.wait_for_attached('#f-js-set option[value="j25"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-set", "Foundations Jumpstart — 121 decks")
    harness.wait_for_attached('#f-js-theme option[value="Angels"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-theme", "Angels (2 variants)")
    harness.wait_for_visible(
        '#f-js-variations label[data-name="Angels (1)"]', timeout=INTERACTION_BUDGET_MS
    )
    harness.click_by_selector("#modal-save-btn")
    harness.wait_for_visible("#deck-builder-root h2", timeout=ROUND_TRIP_BUDGET_MS)

    # Wait for btn-acquire to appear, then click it.
    harness.wait_for_visible("#btn-acquire", timeout=ROUND_TRIP_BUDGET_MS)
    harness.click_by_selector("#btn-acquire")

    # After the acquire + reload, navigate to the batches page.
    harness.wait_for_visible("#btn-acquire", timeout=ROUND_TRIP_BUDGET_MS)
    harness.navigate("/batches")

    # The newest batch should have the "Deck" label, not the raw "deck_acquire" string.
    harness.wait_for_visible(".batch-type-badge", timeout=ROUND_TRIP_BUDGET_MS)
    harness.assert_text_present("Deck")
    harness.assert_text_absent("deck_acquire")

    harness.screenshot("final_state")
