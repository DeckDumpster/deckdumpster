"""
Hand-written implementation for decks_acquire_repeat_warning.

Creates a Jumpstart deck, acquires it once, then clicks "Add to Collection"
again to trigger the in-page repeat-acquire warning (#acquire-warning).
Verifies Cancel dismisses it, then verifies "Add anyway" proceeds.
"""

from tests.ui.budget import INTERACTION_BUDGET_MS, ROUND_TRIP_BUDGET_MS


def steps(harness):
    # Create an Angels (1) Jumpstart deck.
    harness.navigate("/decks")
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=ROUND_TRIP_BUDGET_MS)
    harness.click_by_selector('.mode-tab[data-mode="jumpstart"]')
    harness.wait_for_visible("#mode-jumpstart.active", timeout=INTERACTION_BUDGET_MS)
    harness.wait_for_attached('#f-js-set option[value="j25"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-set", "Foundations Jumpstart — 121 decks")
    harness.wait_for_attached('#f-js-theme option[value="Angels"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-theme", "Angels (2 variants)")
    harness.wait_for_visible(
        '#f-js-variations label[data-name="Angels (1)"]', timeout=INTERACTION_BUDGET_MS
    )
    harness.click_by_selector("#modal-save-btn")
    harness.wait_for_visible("#deck-builder-root h2", timeout=ROUND_TRIP_BUDGET_MS)

    # First acquire — no warning, fires directly.
    harness.wait_for_visible("#btn-acquire", timeout=ROUND_TRIP_BUDGET_MS)
    harness.click_by_selector("#btn-acquire")

    # Wait for reload and flash to confirm the first acquire landed.
    harness.wait_for_visible("#btn-acquire", timeout=ROUND_TRIP_BUDGET_MS)

    # Second acquire — in-page warning must appear.
    harness.click_by_selector("#btn-acquire")
    harness.wait_for_visible("#acquire-warning", timeout=ROUND_TRIP_BUDGET_MS)
    harness.assert_text_present("You already added this deck's cards")

    # Cancel dismisses the warning.
    harness.click_by_selector("#acquire-cancel-btn")
    harness.wait_for_hidden("#acquire-warning", timeout=INTERACTION_BUDGET_MS)

    # Third acquire attempt — warning appears again.
    harness.click_by_selector("#btn-acquire")
    harness.wait_for_visible("#acquire-warning", timeout=ROUND_TRIP_BUDGET_MS)

    # "Add anyway" proceeds with the acquire.
    harness.click_by_selector("#acquire-confirm-btn")

    # Flash banner appears after the reload.
    harness.wait_for_visible("#deck-flash", timeout=ROUND_TRIP_BUDGET_MS)
    harness.assert_text_present("card(s) to your collection")

    harness.screenshot("final_state")
