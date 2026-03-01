"""
Hand-written implementation for sealed_add_and_table_view.

Adds a sealed product and verifies it appears in the table view.
The demo fixture already has some sealed products loaded.
"""


def steps(harness):
    # Click the "+ Add" button to open the add modal.
    harness.click_by_selector("#add-btn")
    # Search for a product.
    harness.fill_by_placeholder("Search sealed products by name...", "Lorwyn")
    # Wait for results and click the first matching product.
    harness.wait_for_visible(".product-results li")
    harness.click_by_selector(".product-results li")
    # Fill in the quantity and confirm.
    harness.click_by_selector("#confirm-add-btn")
    # Close the modal overlay if still visible.
    harness.wait_for_hidden("#add-modal-overlay.active", timeout=5_000)
    # Switch to table view.
    harness.click_by_selector("#view-table-btn")
    # Verify the product appears in the table.
    harness.wait_for_text("Lorwyn")
    harness.screenshot("final_state")
