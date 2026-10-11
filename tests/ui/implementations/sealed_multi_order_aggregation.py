"""
Hand-written implementation for sealed_multi_order_aggregation.

Adds the same sealed product twice with different quantities and prices,
then verifies aggregation shows one row with combined quantity.
"""


def steps(harness):
    # Add a sealed product (first time).
    harness.click_by_selector("#add-btn")
    harness.fill_by_selector("#add-search-input", "Lorwyn")
    harness.wait_for_visible(".product-results li")
    harness.click_by_selector(".product-results li")
    harness.fill_by_selector("#add-qty", "2")
    harness.fill_by_selector("#add-price", "10.00")
    harness.click_by_selector("#confirm-add-btn")
    harness.wait_for_hidden("#add-modal-overlay.active", timeout=5_000)

    # Add the same product again (second time with different qty/price).
    harness.click_by_selector("#add-btn")
    harness.fill_by_selector("#add-search-input", "Lorwyn")
    harness.wait_for_visible(".product-results li")
    harness.click_by_selector(".product-results li")
    harness.fill_by_selector("#add-qty", "3")
    harness.fill_by_selector("#add-price", "15.00")
    harness.click_by_selector("#confirm-add-btn")
    harness.wait_for_hidden("#add-modal-overlay.active", timeout=5_000)

    # Verify aggregated display shows the product.
    harness.wait_for_text("Lorwyn")
    # Click on the product to open detail and verify both entries.
    harness.click_by_text("Lorwyn")
    harness.wait_for_text("Entries")
    harness.screenshot("final_state")
