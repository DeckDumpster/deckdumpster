"""
Hand-written implementation for deck_grid_view_toggle.

Verifies switching between table and grid view on the deck detail page.
"""


def steps(harness):
    # Navigate to the deck detail page
    harness.navigate("/decks/2")

    # Wait for cards to load in table view
    harness.wait_for_visible("#card-table")

    # Verify table is visible and grid is hidden by default
    harness.assert_visible("#card-table")
    harness.assert_hidden("#card-grid")
    harness.screenshot("table_view")

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")

    # Verify grid is visible with card images, table is hidden
    harness.wait_for_visible("#card-grid")
    harness.assert_hidden("#card-table")
    harness.assert_visible("#card-grid .sheet-card")
    harness.screenshot("grid_view")

    # Switch back to table view
    harness.click_by_selector("#view-table-btn")

    # Verify table is visible again
    harness.wait_for_visible("#card-table")
    harness.assert_hidden("#card-grid")

    harness.screenshot("final_state")
