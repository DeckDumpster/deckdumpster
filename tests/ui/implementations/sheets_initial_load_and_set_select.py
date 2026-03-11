"""
Hand-written implementation for sheets_initial_load_and_set_select.

Loads the sheets page, waits for set input to enable, searches for
Bloomburrow, selects it, and verifies product pills appear.
"""


def steps(harness):
    # start_page: /sheets — auto-navigated by test runner.

    # Wait for sets to finish loading (input becomes enabled)
    harness.wait_for_visible("#set-input:not([disabled])")

    # Verify status shows sets loaded
    harness.wait_for_text("sets loaded")

    # Type partial name to filter the dropdown
    harness.fill_by_selector("#set-input", "Bloom")
    harness.wait_for_visible("#set-dropdown li")

    # Select the first matching set (Bloomburrow)
    harness.click_by_selector("#set-dropdown li")

    # Wait for product radio labels to appear
    harness.wait_for_visible("#product-radios label")

    # Verify the input now shows the selected set
    harness.assert_text_present("Bloomburrow")

    harness.screenshot("final_state")
