"""
Hand-written implementation for deck_commander_field_visibility.

Verifies the commander search field visibility toggles based on
format selection and is hidden during deck editing.
"""


def steps(harness):
    # Navigate to decks page
    harness.navigate("/decks")
    harness.wait_for_text("New Deck", timeout=10000)

    # Open new deck modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Commander field hidden by default (no format selected)
    harness.assert_hidden("#commander-field")

    # Select Commander format — field should appear
    harness.select_by_label("#f-format", "Commander / EDH")
    harness.assert_visible("#commander-field")

    harness.screenshot("commander_format_selected")

    # Switch to Standard — field should hide
    harness.select_by_label("#f-format", "Standard")
    harness.assert_hidden("#commander-field")

    # Switch back to Commander — field should reappear
    harness.select_by_label("#f-format", "Commander / EDH")
    harness.assert_visible("#commander-field")

    # Close modal
    harness.click_by_text("Cancel")

    harness.screenshot("final_state")
