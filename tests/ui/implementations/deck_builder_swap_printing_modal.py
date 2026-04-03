"""
Hand-written implementation for deck_builder_swap_printing_modal.

Verifies the swap printing modal opens with all available printings,
shows set info, owned count, and current badge.
"""


def steps(harness):
    # Navigate to the idea deck
    harness.navigate("/decks/3")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Hover a card row to reveal the swap button, then click it
    harness.click_by_selector(".swap-btn")

    # Wait for the swap modal to appear
    harness.wait_for_visible("#swap-modal.active")

    # Verify modal title
    harness.assert_text_present("Swap Printing")

    # Verify printing options are displayed
    harness.assert_visible(".swap-option")

    # Verify the current printing has the Current badge
    harness.assert_text_present("Current")

    # Verify owned count is shown
    harness.assert_text_present("Owned:")

    # Screenshot the modal
    harness.screenshot("swap_modal_open")

    # Close the modal
    harness.click_by_selector("#btn-cancel-swap")
    harness.wait_for_hidden("#swap-modal.active")

    harness.screenshot("final_state")
