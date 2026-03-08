"""
Hand-written implementation for batches_detail_view_and_metadata.

Opens a batch detail view, verifies cards and metadata, then navigates back.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    # Wait for the batch list to load
    harness.wait_for_text("New cards from LGS")
    # Click on the "New cards from LGS" batch to open detail view
    harness.click_by_text("New cards from LGS")
    # Wait for detail view to load with cards
    harness.wait_for_text("Judith, Carnage Connoisseur")
    # Verify batch metadata is shown
    harness.assert_text_present("Corner")
    harness.assert_text_present("4 card(s)")
    # Verify other cards are listed
    harness.assert_text_present("Orazca Puzzle-Door")
    harness.screenshot("detail_view")
    # Click the Back button to return to list
    harness.click_by_text("Back")
    # Verify we're back on the list view
    harness.wait_for_text("Wednesday evening scan")
    harness.screenshot("final_state")
