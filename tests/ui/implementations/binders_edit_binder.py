"""
Hand-written implementation for binders_edit_binder.

Opens Trade Binder, edits its name and color, and verifies the detail
view updates in place.
"""


def steps(harness):
    # start_page: /binders — auto-navigated by test runner.
    harness.wait_for_text("Trade Binder")

    # Click into Trade Binder detail
    harness.click_by_text("Trade Binder")
    harness.wait_for_visible(".detail-view.active")

    # Click Edit
    harness.click_by_text("Edit")

    # Wait for modal
    harness.wait_for_visible("#binder-modal.active")

    # Verify modal title
    harness.assert_text_present("Edit Binder")

    # Clear and update name
    harness.fill_by_selector("#f-name", "Updated Trade Binder")

    # Clear and update color
    harness.fill_by_selector("#f-color", "green")

    # Save
    harness.click_by_text("Save")

    # Verify detail view updates
    harness.wait_for_text("Updated Trade Binder")
    harness.assert_text_present("green")

    harness.screenshot("final_state")
