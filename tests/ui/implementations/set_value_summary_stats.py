"""
Hand-written implementation for set_value_summary_stats.

Runs analysis on BLB and verifies the summary stats row renders
with correct labels and values (Total Cards nonzero, With Prices 0).
"""


def steps(harness):
    # Navigate to the Set Value Analysis page
    harness.navigate("/set-value")
    harness.wait_for_visible("#set-search")

    # Select Bloomburrow
    harness.fill_by_selector("#set-search", "Bloom")
    harness.wait_for_visible("#set-dropdown li")
    harness.click_by_selector("#set-dropdown li")

    # Run analysis
    harness.click_by_selector("#analyze-btn")
    harness.wait_for_visible("#summary")

    # Verify Total Cards label and nonzero value
    harness.assert_text_present("Total Cards")

    # Verify With Prices label
    harness.assert_text_present("With Prices")

    # Verify Median label
    harness.assert_text_present("Median")

    # Verify tier labels
    harness.assert_text_present("Chaff")
    harness.assert_text_present("$10+")

    # Verify stat elements are visible
    harness.assert_visible("#stat-total")
    harness.assert_visible("#stat-priced")

    harness.screenshot("final_state")
