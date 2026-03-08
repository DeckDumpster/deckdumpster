"""
Hand-written implementation for crack_pack_normal_mode.

Opens a pack in normal mode with surprise disabled, verifies all cards
appear face-up immediately with set info in the header.
"""


def steps(harness):
    # Navigate to Crack-a-Pack page
    harness.navigate("/crack")
    harness.wait_for_visible("#set-input")

    # Search for Foundations set
    harness.fill_by_selector("#set-input", "Foundations")
    harness.wait_for_visible("#set-dropdown li")

    # Select the first matching set
    harness.click_by_selector("#set-dropdown li")

    # Wait for product type labels to load (radio inputs are display:none)
    harness.wait_for_visible("#product-radios label")

    # Uncheck surprise mode (click label, input is hidden)
    harness.click_by_selector("label[for='open-mode']")

    # Open the pack
    harness.click_by_selector("#open-btn")

    # Wait for cards to appear
    harness.wait_for_visible(".card-slot")

    # Verify pack header shows set info
    harness.assert_text_present("fdn")

    # No cards should be face-down in normal mode
    harness.assert_hidden(".card-slot.face-down")

    harness.screenshot("final_state")
