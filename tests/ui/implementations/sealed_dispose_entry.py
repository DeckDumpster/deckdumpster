"""
Hand-written implementation for sealed_dispose_entry.

Opens the detail modal for the Outlaws of Thunder Junction Bundle,
expands the edit pane, disposes the entry as "sold" with a sale price.
"""


def steps(harness):
    # Wait for sealed products to load
    harness.wait_for_visible("[data-uuid]")

    # Click the Outlaws bundle to open detail modal (uuid for entry id=5)
    harness.click_by_selector('[data-uuid="dc7bb271-735d-5f5d-9b51-13c644819bb3"]')
    harness.wait_for_visible("#detail-modal-overlay.active")

    # Expand the edit pane
    harness.click_by_selector(".entry-edit-toggle")
    harness.wait_for_visible(".entry-edit-pane.open")

    # Select "sold" from the dispose dropdown
    harness.select_by_label(".ee-dispose-status", "sold")

    # Enter a sale price
    harness.fill_by_selector(".ee-dispose-price", "55")

    # Click Dispose
    harness.click_by_selector(".entry-dispose-btn")

    # Wait for modal to refresh showing sold status
    harness.wait_for_text("sold")
    harness.screenshot("final_state")
