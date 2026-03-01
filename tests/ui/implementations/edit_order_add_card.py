"""
Hand-written implementation for edit_order_add_card.

Navigates to an order's edit page, searches for a card, and adds it.
The demo fixture has order ID 1 (DEMO-TCG-001 from CardHaus Gaming).
"""


def steps(harness):
    # First go to collection and switch to orders view to find an order.
    harness.navigate("/collection")
    harness.wait_for_visible("#view-orders-btn", timeout=10_000)
    harness.click_by_selector("#view-orders-btn")
    harness.wait_for_text("CardHaus Gaming")
    # Click the "Edit" link to go to the order edit page.
    harness.click_by_text("Edit")
    # Wait for the edit page to load.
    harness.wait_for_text("+ Add Card")
    # Click "+ Add Card" to open the search overlay.
    harness.click_by_text("+ Add Card")
    # Search for a card.
    harness.fill_by_placeholder("Search for a card...", "Scrawling Crawler")
    # Wait for search results and click a candidate.
    harness.wait_for_visible(".search-candidate")
    harness.click_by_selector(".search-candidate")
    harness.screenshot("final_state")
