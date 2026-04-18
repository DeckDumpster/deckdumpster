"""
Hand-written implementation for collection_table_virtual_scroll_renders_cards.

Verifies the collection table renders with column headers and card data rows
using virtual scrolling (only visible rows in the DOM).
"""


def steps(harness):
    # Navigate to collection page (default table view)
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=5_000)
    harness.wait_for_visible("#vtbody tr[data-idx]", timeout=5_000)

    # Verify column headers are present
    harness.assert_text_present("Card")
    harness.assert_text_present("Type")
    harness.assert_text_present("Cost")
    harness.assert_text_present("Set")

    # Verify card data rows are rendered
    harness.assert_visible(".card-name")
    harness.assert_visible(".card-thumb")

    harness.screenshot("final_state")
