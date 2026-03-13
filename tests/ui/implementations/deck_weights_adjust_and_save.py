"""
Hand-written implementation for deck_weights_adjust_and_save.

Sets a plan, resets weights to defaults, opens the Weights modal,
increments the Price weight twice using the + button, saves, then
reopens to verify persistence.
"""


def steps(harness):
    # Set plan and reset weights to defaults
    harness.page.evaluate(
        "fetch('/api/decks/2/plan', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({targets: {ramp: 8, removal: 5, draw: 4}})})"
    )
    harness.page.evaluate(
        "fetch('/api/decks/2/weights', "
        "{method: 'POST', headers: {'Content-Type': 'application/json'}, "
        "body: JSON.stringify({edhrec:3,salt:2,price:1,plan_overlap:3,novelty:3,bling:4,random:2})})"
    )
    harness.page.wait_for_timeout(500)

    # Navigate to deck detail page
    harness.navigate("/decks/2")
    harness.wait_for_visible("#plan-section", timeout=10_000)

    # Open weights modal
    harness.click_by_selector("#btn-weights")
    harness.wait_for_visible("#weights-modal.active", timeout=5_000)

    # Verify price starts at 1
    harness.wait_for_visible("#wv-price", timeout=3_000)
    price_el = harness.page.locator("#wv-price")
    assert price_el.text_content().strip() == "1", f"Expected price=1, got {price_el.text_content()}"

    # Click + for price twice (1 -> 2 -> 3)
    harness.click_by_selector('.weight-btn[data-key="price"][data-dir="1"]')
    harness.page.wait_for_timeout(200)
    harness.click_by_selector('.weight-btn[data-key="price"][data-dir="1"]')
    harness.page.wait_for_timeout(200)

    # Verify price is now 3
    price_el = harness.page.locator("#wv-price")
    assert price_el.text_content().strip() == "3", f"Expected price=3, got {price_el.text_content()}"

    # Save
    harness.click_by_selector("#btn-weights-save")
    harness.wait_for_hidden("#weights-modal.active", timeout=5_000)

    # Reopen modal to verify persistence
    harness.click_by_selector("#btn-weights")
    harness.wait_for_visible("#weights-modal.active", timeout=5_000)
    harness.wait_for_visible("#wv-price", timeout=3_000)

    price_el = harness.page.locator("#wv-price")
    assert price_el.text_content().strip() == "3", f"Expected persisted price=3, got {price_el.text_content()}"

    harness.screenshot("final_state")
