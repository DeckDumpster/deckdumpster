"""
Hand-written implementation for sealed_delete_entry.

Opens the detail modal for the Duskmourn Bundle (single entry, qty=1),
expands the edit pane, deletes the entry. Confirm dialog is auto-accepted.
The product disappears from the collection.
"""


def steps(harness):
    # Wait for sealed products to load
    harness.wait_for_visible("[data-uuid]")

    # Click the Duskmourn Bundle card to open detail modal (uuid for entry id=6)
    harness.click_by_selector('[data-uuid="989edd8e-fba0-5102-9dad-178755d59c74"]')
    harness.wait_for_visible("#detail-modal-overlay.active")

    # Expand the edit pane
    harness.click_by_selector(".entry-edit-toggle")
    harness.wait_for_visible(".entry-edit-pane.open")

    # Click Delete (confirm dialog auto-accepted)
    harness.click_by_selector(".entry-delete-btn")

    # Modal closes and collection re-fetches
    harness.wait_for_hidden("#detail-modal-overlay.active", timeout=500)

    # Verify the product is gone (its UUID should no longer be in the DOM)
    harness.assert_hidden('[data-uuid="989edd8e-fba0-5102-9dad-178755d59c74"]')

    harness.screenshot("final_state")
