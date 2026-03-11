"""
Hand-written implementation for edit_order_load_and_view.

Loads the edit order page and verifies all metadata fields, summary bar,
and card row elements are present.
"""


def steps(harness):
    # start_page: /edit-order?id=1 — auto-navigated by test runner.
    harness.wait_for_visible("#save-meta-btn", timeout=10_000)
    # Verify seller name is pre-filled.
    harness.assert_visible("#meta-seller")
    # Verify order number field.
    harness.assert_visible("#meta-order-num")
    # Verify date field.
    harness.assert_visible("#meta-date")
    # Verify source dropdown.
    harness.assert_visible("#meta-source")
    # Verify financial fields.
    harness.assert_visible("#meta-subtotal")
    harness.assert_visible("#meta-shipping")
    harness.assert_visible("#meta-tax")
    harness.assert_visible("#meta-total")
    # Verify Save Order Details button.
    harness.assert_text_present("Save Order Details")
    # Verify summary bar with card count.
    harness.wait_for_visible(".summary-bar", timeout=10_000)
    harness.assert_text_present("5 cards")
    # Verify Add Card button.
    harness.assert_visible("#add-card-btn")
    # Verify at least one card row.
    harness.assert_visible(".card-row")
    # Verify card row has controls.
    harness.assert_visible("select[data-field='condition']")
    harness.assert_visible("select[data-field='finish']")
    harness.assert_visible("input[data-field='purchase_price']")
    harness.screenshot("final_state")
