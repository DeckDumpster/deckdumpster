"""
Hand-written implementation for binders_create_with_all_fields.

Creates a new binder with all optional fields and verifies they appear
in the detail view.
"""


def steps(harness):
    # start_page: /binders — auto-navigated by test runner.
    harness.wait_for_text("Trade Binder")

    # Click New Binder
    harness.click_by_text("New Binder")

    # Wait for modal to appear
    harness.wait_for_visible("#binder-modal.active")

    # Fill in all fields
    harness.fill_by_selector("#f-name", "Rare Binder")
    harness.fill_by_selector("#f-description", "High-value rares")
    harness.fill_by_selector("#f-color", "red")
    harness.select_by_label("#f-type", "4-Pocket")
    harness.fill_by_selector("#f-location", "top shelf")

    # Click Save
    harness.click_by_text("Save")

    # Wait for detail view to load with the new binder
    harness.wait_for_text("Rare Binder")

    # Verify all metadata fields are visible
    harness.assert_text_present("High-value rares")
    harness.assert_text_present("red")
    harness.assert_text_present("4-pocket")
    harness.assert_text_present("top shelf")

    harness.screenshot("final_state")
