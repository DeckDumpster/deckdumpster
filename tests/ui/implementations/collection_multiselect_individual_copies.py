"""
Hand-written implementation for collection_multiselect_individual_copies.

Enables multi-select on the collection page, verifies individual copy rows
appear for Scrawling Crawler, selects the unassigned copy, and assigns it
to deck 2 (Eldrazi Ramp).
"""


def steps(harness):
    # Navigate to collection and search
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=500)
    harness.fill_by_placeholder("Search cards...", "Scrawling Crawler")
    harness.wait_for_visible("tr[data-idx]")

    # Enable multi-select (triggers re-fetch with expand=copies)
    harness.click_by_selector("#more-menu-btn")
    harness.click_by_selector("#toggle-multiselect-btn")

    # Wait for re-fetch with expanded rows
    harness.wait_for_visible("tr[data-idx]")
    harness.screenshot("expanded_individual_copies")

    # Select first checkbox
    harness.click_by_selector("tr[data-idx] input.row-sel-cb")

    # Assign to deck
    harness.click_by_selector("#sel-deck-btn")
    harness.wait_for_visible("#assign-deck-overlay")
    harness.select_by_label("#assign-deck-select", "Eldrazi Ramp")
    harness.click_by_text("Add", exact=True)
    harness.wait_for_hidden("#assign-deck-overlay")

    harness.screenshot("final_state")
