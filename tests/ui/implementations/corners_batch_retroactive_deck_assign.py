"""
Hand-written implementation for corners_batch_retroactive_deck_assign.

Opens an unassigned corner batch and assigns it to an existing deck.
Verifies the assignment succeeds.
"""


def steps(harness):
    # start_page: /batches — auto-navigated by test runner.
    harness.wait_for_visible(".batch-card", timeout=10_000)
    # Click the unassigned "New cards from LGS" batch.
    harness.click_by_text("New cards from LGS")
    # Wait for detail view with the assign section.
    harness.wait_for_visible("#detail-view", timeout=5_000)
    harness.wait_for_visible("#assign-deck-select", timeout=5_000)
    # Select "Bolt Tribal" from the deck dropdown.
    harness.select_by_label("#assign-deck-select", "Bolt Tribal (modern)")
    # Select zone.
    harness.select_by_label("#assign-zone-select", "Mainboard")
    # Click the "Assign" button.
    harness.click_by_text("Assign", exact=True)
    # After assignment, loadBatches() switches back to list view.
    # Wait for the batch card to show the deck assignment.
    harness.wait_for_text("Deck: Bolt Tribal", timeout=10_000)
    harness.screenshot("final_state")
