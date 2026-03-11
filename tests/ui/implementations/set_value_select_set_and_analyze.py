"""
Hand-written implementation for set_value_select_set_and_analyze.

Selects a set via search, verifies pill appears and Analyze enables,
runs analysis, and verifies all result sections become visible.
"""


def steps(harness):
    # Navigate to the Set Value Analysis page
    harness.navigate("/set-value")
    harness.wait_for_visible("#set-search")

    # Type partial name to filter the dropdown
    harness.fill_by_selector("#set-search", "Bloom")
    harness.wait_for_visible("#set-dropdown li")

    # Click the first matching set (Bloomburrow)
    harness.click_by_selector("#set-dropdown li")

    # Verify a selected pill appears
    harness.wait_for_visible(".selected-pill")

    # Click Analyze to run the analysis
    harness.click_by_selector("#analyze-btn")

    # Wait for loading to finish and results to appear
    harness.wait_for_visible("#filter-bar")

    # Verify all result sections are now visible
    harness.assert_visible("#summary")
    harness.assert_visible("#chart-wrap")
    harness.assert_visible("#top-cards")

    # Verify empty state is gone
    harness.assert_hidden("#empty-state")

    harness.screenshot("final_state")
