"""
Hand-written implementation for csv_import_with_batch_metadata.

Verifies the CSV Import page has optional batch metadata fields.
"""


def steps(harness):
    # Navigate to the CSV Import page
    harness.navigate("/import-csv")
    # Verify the batch name input is present
    harness.assert_visible("#batch-name")
    # Verify the product type dropdown is present
    harness.assert_visible("#product-type")
    # Verify the set code input is present
    harness.assert_visible("#batch-set-code")
    # Fill in batch metadata to confirm the fields are interactive
    harness.fill_by_placeholder("e.g. Foundations Starter Collection", "Test Batch")
    harness.fill_by_placeholder("Set", "FDN")
    harness.screenshot("final_state")
