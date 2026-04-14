"""
Hand-written implementation for corners_batch_retroactive_deck_assign.

Opens an unassigned corner batch and assigns it to an existing deck.
Verifies the assignment succeeds.
"""


def steps(harness):
    # start_page: /batches — auto-navigated by test runner.
    harness.wait_for_visible(".batch-card", timeout=500)
    # Click the unassigned "New cards from LGS" batch.
    harness.click_by_text("New cards from LGS")
    # Wait for detail view with the assign section.
    harness.wait_for_visible("#detail-view", timeout=500)
    harness.wait_for_visible("#assign-deck-select", timeout=500)
    # Select "Bolt Tribal" from the deck dropdown.
    harness.select_by_label("#assign-deck-select", "Bolt Tribal (modern)")
    # Select zone.
    harness.select_by_label("#assign-zone-select", "Mainboard")
    # Click the "Assign" button.
    harness.click_by_text("Assign", exact=True)
    # After assignment, batch_detail.html re-renders in place and the
    # assign-status div replaces the form with "Assigned to: X (zone)".
    harness.wait_for_text("Assigned to: Bolt Tribal", timeout=500)
    harness.screenshot("final_state")
