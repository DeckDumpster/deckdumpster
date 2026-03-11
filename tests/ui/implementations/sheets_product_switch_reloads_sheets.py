"""
Hand-written implementation for sheets_product_switch_reloads_sheets.

Selects BLB, confirms collector loads first, switches to play product,
and verifies different sheet names appear.
"""


def steps(harness):
    # start_page: /sheets — auto-navigated by test runner.

    # Wait for sets to finish loading (input becomes enabled)
    harness.wait_for_visible("#set-input:not([disabled])")

    # Select Bloomburrow
    harness.fill_by_selector("#set-input", "Bloom")
    harness.wait_for_visible("#set-dropdown li")
    harness.click_by_selector("#set-dropdown li")

    # Wait for product pills and sheets to load (collector is first)
    harness.wait_for_visible("#product-radios label")
    harness.wait_for_visible(".section-header")

    # Collector has 6 sheets -- verify status shows collector sheet count
    harness.assert_text_present("6 sheets")

    # Click the "play" product label (radio inputs are display:none)
    harness.click_by_text("play", exact=True)

    # Wait for sheets to reload with play product content (8 sheets for play)
    harness.wait_for_text("8 sheets")

    harness.screenshot("final_state")
