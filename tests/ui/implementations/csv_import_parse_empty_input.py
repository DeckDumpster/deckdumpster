"""
Hand-written implementation for csv_import_parse_empty_input.

Clicks Parse & Resolve with empty input and verifies the error message.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Click Parse & Resolve with no input
    harness.click_by_selector("#parse-btn")

    # Verify error message
    harness.assert_text_present("No CSV text provided.")

    harness.screenshot("final_state")
