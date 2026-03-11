"""
Hand-written implementation for binders_remove_cards.

Opens Trade Binder, selects a card via checkbox, removes it, and
verifies the card disappears from the table.
"""


def steps(harness):
    # Navigate to the Binders page
    harness.navigate("/binders")
    harness.wait_for_text("Trade Binder")

    # Click into Trade Binder
    harness.click_by_text("Trade Binder")
    harness.wait_for_visible(".detail-view.active")

    # Wait for card table to populate
    harness.wait_for_text("Acrobatic Cheerleader")

    # Click the checkbox for the first card row
    harness.click_by_selector("#card-tbody tr:first-child input[type='checkbox']")

    # Click Remove Selected
    harness.click_by_text("Remove Selected")

    # Verify the card is removed
    harness.wait_for_text("5")
    harness.assert_text_absent("Acrobatic Cheerleader")

    harness.screenshot("final_state")
