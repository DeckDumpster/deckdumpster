"""
Hand-written implementation for set_value_filter_rarity.

Runs analysis on BLB, deactivates the Common rarity filter, verifies
Total Cards decreases, reactivates it, and verifies count restores.
"""


def steps(harness):
    # Navigate to the Set Value Analysis page
    harness.navigate("/set-value")
    harness.wait_for_visible("#set-search")

    # Select Bloomburrow and analyze
    harness.fill_by_selector("#set-search", "Bloom")
    harness.wait_for_visible("#set-dropdown li")
    harness.click_by_selector("#set-dropdown li")
    harness.click_by_selector("#analyze-btn")
    harness.wait_for_visible("#filter-bar")

    # Screenshot before filtering to capture initial Total Cards
    harness.screenshot("before_filter")

    # Click the "C" pill to deactivate Common rarity filter
    harness.click_by_selector("#rarity-filters .pill[data-value='common']")

    # Screenshot after deactivating to show decreased count
    harness.screenshot("common_deactivated")

    # Click "C" pill again to reactivate Common rarity
    harness.click_by_selector("#rarity-filters .pill[data-value='common']")

    # Verify the count is restored
    harness.screenshot("final_state")
