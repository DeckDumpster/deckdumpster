"""
Hand-written implementation for batches_assign_unassigned_to_deck.

Assigns the unassigned batch "New cards from LGS" to the "Eldrazi Ramp" deck.
"""


def steps(harness):
    # start_page: /batches — auto-navigated by test runner.
    harness.wait_for_text("New cards from LGS")

    # Click on the unassigned batch
    harness.click_by_text("New cards from LGS")

    # Wait for detail view with assignment controls
    harness.wait_for_visible("#assign-deck-select")

    # Select "Eldrazi Ramp" from deck dropdown
    harness.select_by_label("#assign-deck-select", "Eldrazi Ramp (commander)")

    # Click the Assign button (use selector to avoid matching "Assign to Deck" label)
    harness.click_by_selector(".assign-row button")

    # After assign, batch_detail.html re-renders in place and the
    # assign-status div replaces the form with "Assigned to: X (zone)".
    harness.wait_for_text("Assigned to: Eldrazi Ramp")
    harness.assert_text_present("Eldrazi Ramp")

    harness.screenshot("final_state")
