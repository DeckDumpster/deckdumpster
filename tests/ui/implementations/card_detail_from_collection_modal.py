"""
Hand-written implementation for card_detail_from_collection_modal.

Opens a card modal from the collection page, clicks the "Full page" link,
and verifies the card detail page loads.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    # Wait for collection table to load.
    harness.wait_for_visible("tr[data-idx]", timeout=500)
    # Switch to grid view for direct card click.
    harness.click_by_selector("#view-grid-btn")
    # Click the first card in grid view to open the modal.
    harness.click_by_selector(".sheet-card[data-idx]")
    # Wait for modal to appear.
    harness.wait_for_visible("#card-modal-overlay.active", timeout=500)
    # Click the "Full page" badge link in the modal.
    harness.click_by_text("Full page")
    # Should navigate to /card/:set/:cn.
    harness.wait_for_visible(".card-detail-layout", timeout=500)
    # Verify a card name heading is present.
    harness.assert_visible("h2")
    harness.screenshot("final_state")
