"""
Hand-written implementation for csv_import_cancel_after_resolve.

Parses and resolves a deck list, clicks Cancel, and verifies the
cancellation message.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Paste valid deck list
    harness.fill_by_selector(
        "#csv-text",
        "1 Beast-Kin Ranger (FDN) 100",
    )

    # Parse & Resolve
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=10000)

    # Cancel
    harness.click_by_selector("#cancel-btn")

    # Verify cancellation message
    harness.assert_text_present("Cancelled. Paste new data to start over.")

    harness.screenshot("final_state")
