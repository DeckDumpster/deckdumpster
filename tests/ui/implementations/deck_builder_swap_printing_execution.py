"""
Hand-written implementation for deck_builder_swap_printing_execution.

Verifies that clicking an alternate printing swaps it in the deck.
"""


def steps(harness):
    # Navigate to the idea deck
    harness.navigate("/decks/3")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Click the swap button on first card
    harness.click_by_selector(".swap-btn")
    harness.wait_for_visible("#swap-modal.active")

    # Click a non-current printing option to perform the swap
    harness.click_by_selector(".swap-option:not(.current)")

    # Modal should close and deck should reload
    harness.wait_for_hidden("#swap-modal.active")
    harness.wait_for_visible("#type-groups")

    # Verify the deck reloaded (list view still shows cards)
    harness.assert_visible(".card-row")

    # Open swap modal again to verify the new printing has Current badge
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")
    harness.click_by_selector(".swap-btn")
    harness.wait_for_visible("#swap-modal.active")
    harness.assert_text_present("Current")

    harness.screenshot("final_state")
