"""
Hand-written implementation for collection_shared_card_list_empty.

Verifies that a shared card list URL with nonexistent cards shows empty results.
"""


def steps(harness):
    # start_page from hints navigates to /collection?cards=zzz:999&view=grid

    # Wait for the page to finish loading
    harness.wait_for_text("0 owned", timeout=10_000)

    # Verify no cards are rendered in the grid
    harness.assert_element_count(".sheet-card", 0)

    harness.screenshot("final_state")
