"""
Hand-written implementation for homepage_price_source_setting.
Verifies Price Sources pills reflect saved state, toggles independently,
checks the Saved indicator, and confirms persistence on reload.
"""


def steps(harness):
    # Navigate to homepage
    harness.navigate("/")

    # Wait for settings to load (both TCG and CK pills active by default)
    harness.wait_for_visible("#price-source-checks .pill.active")

    # Verify both pills are active
    harness.assert_visible("#price-source-checks .pill[data-value='tcg'].active")
    harness.assert_visible("#price-source-checks .pill[data-value='ck'].active")

    # Click TCG pill to deactivate it
    harness.click_by_selector("#price-source-checks .pill[data-value='tcg']")

    # Verify Saved indicator appears
    harness.wait_for_visible("#save-status.visible")

    # Reload page to verify persistence
    harness.navigate("/")
    harness.wait_for_visible("#price-source-checks .pill.active")

    # Verify only CK is active after reload (TCG was deactivated)
    harness.assert_visible("#price-source-checks .pill[data-value='ck'].active")
    harness.assert_hidden("#price-source-checks .pill[data-value='tcg'].active")

    # Re-enable TCG pill
    harness.click_by_selector("#price-source-checks .pill[data-value='tcg']")
    harness.wait_for_visible("#save-status.visible")

    harness.screenshot("final_state")
