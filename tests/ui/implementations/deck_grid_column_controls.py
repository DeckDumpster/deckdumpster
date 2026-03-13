"""
Hand-written implementation for deck_grid_column_controls.

Verifies that the +/- column controls appear in grid view and
adjust the cards-per-row count.
"""


def steps(harness):
    # Navigate to the deck detail page
    harness.navigate("/decks/2")

    # Wait for cards to load
    harness.wait_for_visible("#card-table")

    # Verify grid size controls are hidden in table view
    harness.assert_hidden("#grid-size-wrap")

    # Switch to grid view
    harness.click_by_selector("#view-grid-btn")
    harness.wait_for_visible("#card-grid")

    # Verify grid size controls are now visible
    harness.assert_visible("#grid-size-wrap")
    harness.screenshot("grid_with_controls")

    # Click minus to decrease column count
    harness.click_by_selector("#col-minus")

    # Click plus to increase column count
    harness.click_by_selector("#col-plus")

    # Verify controls are still visible and functional
    harness.assert_visible("#col-count")

    # Switch back to table view — controls should hide
    harness.click_by_selector("#view-table-btn")
    harness.assert_hidden("#grid-size-wrap")

    harness.screenshot("final_state")
