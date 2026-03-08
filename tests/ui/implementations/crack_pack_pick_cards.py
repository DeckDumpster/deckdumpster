"""
Hand-written implementation for crack_pack_pick_cards.

Opens a pack in normal mode, picks a card, and verifies it appears
in the pick list sidebar.
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

    # Uncheck surprise mode for normal (face-up) mode (click label, input is hidden)
    harness.click_by_selector("label[for='open-mode']")

    # Open the pack
    harness.click_by_selector("#open-btn")

    # Wait for cards to appear face-up
    harness.wait_for_visible(".card-slot")

    # Click a card to pick it
    harness.click_by_selector(".card-slot")

    # Verify the card was added to the pick list
    harness.wait_for_visible("#pick-list .pick-item")
    harness.assert_text_present("(1)")

    harness.screenshot("final_state")
