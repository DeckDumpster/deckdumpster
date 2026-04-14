"""
Hand-written implementation for edit_order_save_metadata.

Changes seller name, source, and shipping, saves, then reloads to verify
persistence.
"""


def steps(harness):
    # start_page: /orders/1 — auto-navigated by test runner.
    harness.wait_for_visible("#save-meta-btn", timeout=500)
    # Change seller name.
    harness.fill_by_selector("#meta-seller", "Test Seller")
    # Change source to Card Kingdom.
    harness.select_by_label("#meta-source", "Card Kingdom")
    # Change shipping cost.
    harness.fill_by_selector("#meta-shipping", "5.99")
    # Click Save Order Details.
    harness.click_by_selector("#save-meta-btn")
    # Wait for green "Saved" confirmation.
    harness.wait_for_visible(".status-msg.success", timeout=500)
    harness.assert_text_present("Saved")
    # Reload and verify persistence.
    harness.navigate("/orders/1")
    harness.wait_for_visible("#save-meta-btn", timeout=500)
    # Seller name is inside an <input> element, so we verify via input_value
    # rather than wait_for_text (which only finds visible text content).
    value = harness.page.input_value("#meta-seller", timeout=500)
    assert value == "Test Seller", f"Expected 'Test Seller', got '{value}'"
    harness.screenshot("final_state")
