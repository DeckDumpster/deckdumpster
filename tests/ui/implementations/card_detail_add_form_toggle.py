"""
Hand-written implementation for card_detail_add_form_toggle.

Opens the add-to-collection form via the Add button, verifies it appears
with pre-filled date, then closes it by clicking Add again.
"""


def steps(harness):
    # start_page: /card/lci/68 — auto-navigated by test runner.
    harness.wait_for_text("Orazca Puzzle-Door")
    harness.wait_for_visible("#add-btn", timeout=500)
    # Click "Add" to open the form.
    harness.click_by_selector("#add-btn")
    # Verify the add form appears.
    harness.wait_for_visible(".add-collection-form", timeout=500)
    # Verify date field is present.
    harness.assert_visible("#add-date")
    # Verify price and source fields are present.
    harness.assert_visible("#add-price")
    harness.assert_visible("#add-source")
    # Click "Add" again to close the form.
    harness.click_by_selector("#add-btn")
    # Verify the form disappears.
    harness.wait_for_hidden(".add-collection-form", timeout=500)
    harness.screenshot("final_state")
