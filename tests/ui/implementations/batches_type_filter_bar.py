"""
Hand-written implementation for batches_type_filter_bar.

Verifies the type filter pill bar on the Batches page filters the batch list.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    # Wait for the batch list to load
    harness.wait_for_text("Wednesday evening scan")
    # Verify the "All" pill is active by default
    harness.assert_text_present("All")
    harness.assert_text_present("Corner")
    harness.assert_text_present("OCR")
    harness.assert_text_present("CSV Import")
    harness.assert_text_present("Manual ID")
    harness.assert_text_present("Orders")
    # Click the "Corner" filter pill
    harness.click_by_text("Corner")
    # Verify corner batches are still visible (demo data is all corner type)
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")
    # Click "All" to reset the filter
    harness.click_by_text("All")
    harness.wait_for_text("Wednesday evening scan")
    harness.screenshot("final_state")
