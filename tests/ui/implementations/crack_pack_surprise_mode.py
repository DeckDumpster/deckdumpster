"""
Hand-written implementation for crack_pack_surprise_mode.

Opens a surprise mode pack, verifies cards are face-down, reveals one card,
then reveals all remaining cards with the Reveal All button.
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

    # Surprise mode is checked by default — open the pack
    harness.click_by_selector("#open-btn")

    # Wait for face-down cards to appear
    harness.wait_for_visible(".card-slot.face-down")
    harness.screenshot("face_down_pack")

    # Click one card to reveal it
    harness.click_by_selector(".card-slot.face-down")

    # Click Reveal All to show remaining cards
    harness.click_by_selector("#reveal-all-btn")

    # All cards should now be face-up
    harness.wait_for_hidden(".card-slot.face-down")
    harness.screenshot("final_state")
