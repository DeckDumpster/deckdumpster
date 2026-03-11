"""
Hand-written implementation for binders_add_cards_full_flow.

Opens Trade Binder, uses the Add Cards picker to search for and add
"Preacher of the Schism", then verifies it appears in the card table.
"""


def steps(harness):
    # Navigate to the Binders page
    harness.navigate("/binders")
    harness.wait_for_text("Trade Binder")

    # Click into Trade Binder
    harness.click_by_text("Trade Binder")
    harness.wait_for_visible(".detail-view.active")

    # Click Add Cards
    harness.click_by_text("Add Cards")

    # Wait for add-cards modal
    harness.wait_for_visible("#add-cards-modal.active")

    # Type search term
    harness.fill_by_placeholder("Search by name...", "pr")

    # Wait for picker results to load
    harness.wait_for_text("Preacher of the Schism")

    # Click to select the card
    harness.click_by_text("Preacher of the Schism")

    # Click Add Selected
    harness.click_by_text("Add Selected")

    # Wait for modal to close and binder to refresh
    harness.wait_for_hidden("#add-cards-modal.active")

    # Verify the card now appears in the binder table
    harness.wait_for_text("Preacher of the Schism")

    harness.screenshot("final_state")
