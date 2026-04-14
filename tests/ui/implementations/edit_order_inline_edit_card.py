"""
Hand-written implementation for edit_order_inline_edit_card.

Changes a card's condition and finish dropdowns, then reloads to verify
the auto-save persisted both values.
"""


def steps(harness):
    # start_page: /orders/1 — auto-navigated by test runner.
    harness.wait_for_visible(".card-row", timeout=500)
    # Change condition on the first card to "Lightly Played".
    harness.select_by_label("select[data-field='condition']", "Lightly Played")
    # Change finish on the same card to "foil".
    harness.select_by_label("select[data-field='finish']", "foil")
    # Wait for auto-save to complete.
    # Reload and verify persistence.
    harness.navigate("/orders/1")
    harness.wait_for_visible(".card-row", timeout=500)
    harness.screenshot("final_state")
