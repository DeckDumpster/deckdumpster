"""
Hand-written implementation for decks_acquire_and_materialize.

Creates a Foundations Jumpstart "Angels (1)" deck via the picker, clicks
"Add to Collection" (confirm/alert auto-accepted), then Materializes. Verifies
that the completeness panel reports zero missing cards.
"""

from tests.ui.budget import INTERACTION_BUDGET_MS, ROUND_TRIP_BUDGET_MS


def steps(harness):
    # Open the modal and switch to the Jumpstart tab.
    harness.navigate("/decks")
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active", timeout=ROUND_TRIP_BUDGET_MS)
    harness.click_by_selector('.mode-tab[data-mode="jumpstart"]')
    harness.wait_for_visible("#mode-jumpstart.active", timeout=INTERACTION_BUDGET_MS)

    # Select Foundations Jumpstart and the Angels theme.
    harness.wait_for_attached('#f-js-set option[value="j25"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-set", "Foundations Jumpstart — 121 decks")
    harness.wait_for_attached('#f-js-theme option[value="Angels"]', timeout=ROUND_TRIP_BUDGET_MS)
    harness.select_by_label("#f-js-theme", "Angels (2 variants)")

    # Variations chips appear; the first chip (Angels (1)) is selected by default.
    harness.wait_for_visible(
        '#f-js-variations label[data-name="Angels (1)"]', timeout=INTERACTION_BUDGET_MS
    )

    # Import the deck — navigates to /decks/:id.
    harness.click_by_selector("#modal-save-btn")
    harness.wait_for_visible("#deck-builder-root h2", timeout=ROUND_TRIP_BUDGET_MS)
    harness.assert_text_present("Angels (1)")

    # loadCompleteness runs asynchronously and shows btn-acquire when expected.length > 0.
    harness.wait_for_visible("#btn-acquire", timeout=ROUND_TRIP_BUDGET_MS)

    # Click Add to Collection.
    # The harness auto-accepts the confirm dialog and the result alert.
    # window.location.reload() fires after the acquire POST completes.
    harness.click_by_selector("#btn-acquire")

    # After the reload, wait for the Materialize button to be visible.
    harness.wait_for_visible("#btn-materialize", timeout=ROUND_TRIP_BUDGET_MS)

    # Click Materialize — confirm is auto-accepted; page reloads again.
    harness.click_by_selector("#btn-materialize")

    # After materialize, the deck is constructed. Completeness shows 0 missing.
    harness.wait_for_visible("#completeness-section", timeout=ROUND_TRIP_BUDGET_MS)
    harness.assert_text_present("0 missing")

    harness.screenshot("final_state")
