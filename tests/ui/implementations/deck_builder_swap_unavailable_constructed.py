"""
Hand-written implementation for deck_builder_swap_unavailable_constructed.

Verifies swap button does not appear on constructed decks but does
appear on idea decks.
"""


def steps(harness):
    # Navigate to constructed deck
    harness.navigate("/decks/1")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Verify no swap buttons exist on constructed deck
    harness.assert_hidden(".swap-btn")

    harness.screenshot("constructed_no_swap")

    # Navigate to idea deck
    harness.navigate("/decks/3")

    # Switch to list view
    harness.click_by_selector("#view-list-btn")
    harness.wait_for_visible("#type-groups")

    # Verify swap buttons exist on idea deck
    harness.assert_visible(".swap-btn")

    harness.screenshot("final_state")
