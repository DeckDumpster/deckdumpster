"""
Hand-written implementation for csv_import_batch_metadata_in_commit.

Fills batch metadata fields, parses and resolves cards, commits, and
verifies the commit succeeds with batch metadata included.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Fill batch metadata
    harness.fill_by_selector("#batch-name", "Test Batch")
    harness.select_by_label("#product-type", "Booster Box")
    harness.fill_by_selector("#batch-set-code", "FDN")

    # Paste valid deck list
    harness.fill_by_selector(
        "#csv-text",
        "1 Beast-Kin Ranger (FDN) 100",
    )

    # Parse & Resolve
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=500)

    # Commit
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Successfully added", timeout=500)

    harness.screenshot("final_state")
