"""
Hand-written implementation for sealed_open_product.

Opens a sealed product via the Open Product modal, previews its contents,
confirms the open, and verifies cards were added to the collection.
"""


def steps(harness):
    # Navigate to sealed collection page
    harness.navigate("/sealed")
    harness.wait_for_visible("#open-btn")

    # Click the Open Product button
    harness.click_by_selector("#open-btn")
    harness.wait_for_visible("#open-modal-overlay.active")

    # Search for Foundations Starter Collection
    harness.fill_by_selector("#open-search-input", "Foundations Starter")
    harness.wait_for_visible("#open-product-results li")

    # Click the Foundations Starter Collection result
    harness.click_by_text("Foundations Starter Collection")

    # Wait for preview to load with card summary
    harness.wait_for_text("cards to add")
    harness.wait_for_visible("#open-confirm-btn")

    # Verify the preview shows key elements
    harness.assert_text_present("cards to add")
    harness.assert_visible("#open-condition")

    # Screenshot the preview state
    harness.screenshot("preview_state")

    # Click the confirm button to open the product
    harness.click_by_selector("#open-confirm-btn")

    # Wait for modal to close and status to update
    harness.wait_for_hidden("#open-modal-overlay.active", timeout=500)
    harness.wait_for_text("Added")

    # Final state: sealed page with status showing added cards
    harness.screenshot("final_state")
