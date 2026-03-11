"""
Hand-written implementation for corners_batch_browse.

Navigates to the batches page, filters for corner batches, and clicks
one to see its cards in the detail view.
"""


def steps(harness):
    # start_page: /batches — auto-navigated by test runner.
    # Wait for the batch list to load.
    harness.wait_for_visible(".batch-card", timeout=10_000)
    # Click the "Corner" filter pill to filter to corner batches.
    harness.click_by_text("Corner", exact=True)
    # Verify corner batches are still visible.
    harness.wait_for_visible(".batch-card", timeout=5_000)
    # Click the "New cards from LGS" batch to open detail view.
    harness.click_by_text("New cards from LGS")
    # Wait for detail view to appear with cards.
    harness.wait_for_visible("#detail-view", timeout=5_000)
    harness.wait_for_visible(".card-item", timeout=5_000)
    # Verify batch metadata is shown.
    harness.assert_text_present("New cards from LGS")
    harness.assert_text_present("Corner")
    harness.screenshot("final_state")
