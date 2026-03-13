"""
Hand-written implementation for deck_weights_reset_defaults.

Sets a plan with custom weights (edhrec=5, price=3), opens the modal,
verifies custom values are shown, clicks Reset to Defaults, verifies
values revert, saves, and reopens to confirm persistence.
"""


def steps(harness):
    # Set plan and custom weights
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {ramp: 8, removal: 5, draw: 4}})})"
    )
    harness.page.evaluate(
        "fetch('/api/decks/2/weights', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({edhrec:5,salt:1,price:3,plan_overlap:3,novelty:3,bling:4,random:2})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")
    harness.wait_for_visible("#plan-section", timeout=10_000)

    # Open weights modal
    harness.click_by_selector("#btn-weights")
    harness.wait_for_visible("#weights-modal.active", timeout=5_000)
    harness.wait_for_visible("#wv-edhrec", timeout=3_000)

    # Verify custom values are loaded
    edhrec_el = harness.page.locator("#wv-edhrec")
    assert edhrec_el.text_content().strip() == "5", f"Expected edhrec=5, got {edhrec_el.text_content()}"
    price_el = harness.page.locator("#wv-price")
    assert price_el.text_content().strip() == "3", f"Expected price=3, got {price_el.text_content()}"
    salt_el = harness.page.locator("#wv-salt")
    assert salt_el.text_content().strip() == "1", f"Expected salt=1, got {salt_el.text_content()}"

    # Click Reset to Defaults
    harness.click_by_text("Reset to Defaults")
    harness.page.wait_for_timeout(300)

    # Verify values reverted to defaults
    edhrec_el = harness.page.locator("#wv-edhrec")
    assert edhrec_el.text_content().strip() == "3", f"Expected edhrec=3 after reset, got {edhrec_el.text_content()}"
    price_el = harness.page.locator("#wv-price")
    assert price_el.text_content().strip() == "1", f"Expected price=1 after reset, got {price_el.text_content()}"
    salt_el = harness.page.locator("#wv-salt")
    assert salt_el.text_content().strip() == "2", f"Expected salt=2 after reset, got {salt_el.text_content()}"

    # Save the reset defaults
    harness.click_by_selector("#btn-weights-save")
    harness.wait_for_hidden("#weights-modal.active", timeout=5_000)

    # Reopen to verify defaults persisted
    harness.click_by_selector("#btn-weights")
    harness.wait_for_visible("#weights-modal.active", timeout=5_000)
    harness.wait_for_visible("#wv-edhrec", timeout=3_000)

    edhrec_el = harness.page.locator("#wv-edhrec")
    assert edhrec_el.text_content().strip() == "3", f"Expected persisted edhrec=3, got {edhrec_el.text_content()}"

    harness.screenshot("final_state")
