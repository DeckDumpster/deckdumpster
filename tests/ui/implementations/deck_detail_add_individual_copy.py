"""
Hand-written implementation for deck_detail_add_individual_copy.

Opens deck 2, searches for Scrawling Crawler in the add-cards picker,
verifies only the one unassigned copy appears, selects it, and adds it.
"""


def steps(harness):
    # Navigate to deck 2 detail page
    harness.navigate("/decks/2")
    harness.wait_for_text("Eldrazi Ramp")

    # Click + Add Card button
    harness.click_by_selector("#add-card-btn")
    harness.wait_for_visible("#add-cards-modal.active")

    # Search for Scrawling Crawler
    harness.fill_by_placeholder("Search by name...", "Scrawling")
    harness.wait_for_text("Scrawling Crawler")

    # Verify only 1 picker row (the unassigned copy)
    harness.assert_element_count(".picker-card", 1)
    harness.screenshot("single_unassigned_copy")

    # Select the copy
    harness.click_by_text("Scrawling Crawler")

    # Add to deck
    harness.click_by_text("Add Selected")
    harness.wait_for_hidden("#add-cards-modal.active")

    # Verify card appears in the deck grid
    harness.wait_for_visible(".grid-card-name")
    harness.assert_text_present("Scrawling Crawler")

    harness.screenshot("final_state")
