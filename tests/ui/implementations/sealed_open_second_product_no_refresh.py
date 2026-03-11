"""
Test that the Open Product search box remains visible across consecutive modal opens.

Opens a sealed product via the modal, closes it, reopens the modal, and
verifies the search input is still visible and functional. Regression test
for a bug where showOpenPreview() hid the search input and closeOpenModal()
never restored it.
"""


def steps(harness):
    # Wait for sealed page to load.
    harness.wait_for_visible("#open-btn")
    # Click "Open Product" to open the modal.
    harness.click_by_selector("#open-btn")
    harness.wait_for_visible("#open-modal-overlay.active")
    # Search for the first product.
    harness.fill_by_selector("#open-search-input", "Foundations Beginner")
    harness.wait_for_visible("#open-product-results li", timeout=10_000)
    # Click the Beginner Box result.
    harness.click_by_text("Foundations Beginner Box")
    # Wait for the preview with confirm button.
    harness.wait_for_visible("#open-confirm-btn", timeout=10_000)
    harness.screenshot("first_product_preview")
    # Open the product.
    harness.click_by_selector("#open-confirm-btn")
    # Wait for modal to close and success feedback.
    harness.wait_for_hidden("#open-modal-overlay.active", timeout=10_000)
    harness.wait_for_text("Added")
    harness.screenshot("first_product_opened")
    # Reopen the modal — this is the regression check.
    harness.click_by_selector("#open-btn")
    harness.wait_for_visible("#open-modal-overlay.active")
    # The search input must be visible. This failed before the fix.
    harness.assert_visible("#open-search-input")
    # Search for a second product to verify full functionality.
    harness.fill_by_selector("#open-search-input", "Foundations Starter")
    harness.wait_for_visible("#open-product-results li", timeout=10_000)
    # Click the Starter Collection result.
    harness.click_by_text("Foundations Starter Collection")
    harness.wait_for_visible("#open-confirm-btn", timeout=10_000)
    harness.screenshot("second_product_preview")
