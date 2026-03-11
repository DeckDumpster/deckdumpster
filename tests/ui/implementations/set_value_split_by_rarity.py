"""
Hand-written implementation for set_value_split_by_rarity.

Runs analysis on BLB, then switches split toggle to Rarity and
verifies the chart re-renders.
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
    harness.wait_for_visible("#chart-wrap")

    # Screenshot before split (default: None)
    harness.screenshot("split_none")

    # Click "Rarity" in the split toggle
    harness.click_by_selector("#split-toggle .pill[data-value='rarity']")

    # Verify chart is still visible after re-render
    harness.assert_visible("#chart-wrap")
    harness.assert_visible("#chart")

    harness.screenshot("final_state")
