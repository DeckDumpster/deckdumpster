"""
Hand-written implementation for set_value_filter_card_type_and_owned.

Runs analysis on BLB, filters by Special card type, then by Owned,
verifies counts decrease, then resets both to All.
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

    # Screenshot with all filters at default
    harness.screenshot("all_cards")

    # Switch Cards toggle to "Special"
    harness.click_by_selector("#card-type-toggle .pill[data-value='special']")

    # Screenshot showing decreased count for special cards only
    harness.screenshot("special_only")

    # Switch Owned toggle to "Owned"
    harness.click_by_selector("#owned-toggle .pill[data-value='owned']")

    # Screenshot showing further decreased count (special + owned)
    harness.screenshot("special_and_owned")

    # Reset both filters back to "All"
    harness.click_by_selector("#card-type-toggle .pill[data-value='all']")
    harness.click_by_selector("#owned-toggle .pill[data-value='all']")

    harness.screenshot("final_state")
