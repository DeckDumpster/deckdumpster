"""
Hand-written implementation for binders_detail_view_empty_card_list.

Creates a new binder and verifies the empty card table message and
header controls on the detail view.
"""


def steps(harness):
    # Navigate to the Binders page
    harness.navigate("/binders")
    harness.wait_for_text("Trade Binder")

    # Click New Binder
    harness.click_by_text("New Binder")
    harness.wait_for_visible("#binder-modal.active")

    # Fill in just the name
    harness.fill_by_selector("#f-name", "Empty Test Binder")

    # Save
    harness.click_by_text("Save")

    # Wait for detail view
    harness.wait_for_text("Empty Test Binder")
    harness.wait_for_visible(".detail-view.active")

    # Verify empty card table message
    harness.assert_text_present("No cards in this binder")

    # Verify header controls are visible
    harness.assert_visible("#detail-controls")
    harness.assert_text_present("Add Cards")
    harness.assert_text_present("Remove Selected")

    harness.screenshot("final_state")
