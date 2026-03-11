"""
Hand-written implementation for sealed_edit_entry.

Opens the detail modal for the Duskmourn Collector Booster Box,
edits the entry's quantity and price, saves, and verifies the update.
"""


def steps(harness):
    # Wait for sealed products to load
    harness.wait_for_visible("[data-uuid]")

    # Click the Duskmourn Collector Booster Box to open detail modal (uuid for entry id=1)
    harness.click_by_selector('[data-uuid="1d087a75-ba5d-55a0-a968-1f7375717b8f"]')
    harness.wait_for_visible("#detail-modal-overlay.active")

    # Click "Edit" to expand the edit pane for the first entry
    harness.click_by_selector(".entry-edit-toggle")
    harness.wait_for_visible(".entry-edit-pane.open")

    # Change quantity to 2
    harness.fill_by_selector(".ee-qty", "2")

    # Change price to 99
    harness.fill_by_selector(".ee-price", "99")

    # Click Save
    harness.click_by_selector(".entry-save-btn")

    # Wait for modal to refresh with updated values
    harness.wait_for_text("99")
    harness.screenshot("final_state")
