"""
Hand-written implementation for deck_plan_tag_filter.

Verifies that clicking a plan category filters the card table to only
cards with that role, and that clearing the filter restores all cards.
"""


def steps(harness):
    # Navigate to the deck detail page
    harness.navigate("/decks/2")

    # Wait for plan section and cards to load
    harness.wait_for_visible("#plan-section")
    harness.wait_for_visible("#card-tbody")

    # Verify all 6 cards are visible initially
    harness.assert_element_count("#card-tbody tr", 6)

    # Click the "ramp" plan category label
    harness.click_by_text("ramp", exact=True)

    # Verify filter banner appears
    harness.wait_for_visible("#active-filter-banner")
    harness.assert_text_present("ramp")

    # Verify only 2 ramp cards are shown
    harness.assert_element_count("#card-tbody tr", 2)
    harness.screenshot("filtered_by_ramp")

    # Click Clear to remove the filter
    harness.click_by_selector("#btn-clear-filter")

    # Verify all 6 cards are visible again
    harness.wait_for_hidden("#active-filter-banner")
    harness.assert_element_count("#card-tbody tr", 6)

    harness.screenshot("final_state")
