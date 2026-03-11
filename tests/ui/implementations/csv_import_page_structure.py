"""
Hand-written implementation for csv_import_page_structure.

Verifies the CSV Import page loads with all expected elements: title, Home link,
textarea, drop zone, format dropdown with 5 options, batch fields, parse button,
and info message.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Verify page title and Home link
    harness.assert_text_present("CSV Import")
    harness.assert_visible("header a[href='/']")

    # Verify textarea
    harness.assert_visible("#csv-text")

    # Verify file drop zone
    harness.assert_visible("#file-drop")
    harness.assert_text_present("Or drop/click to upload a .csv file")

    # Verify format dropdown with options
    harness.assert_visible("#format-select")
    harness.assert_text_present("Auto-detect")
    harness.assert_text_present("Deck List (text)")
    harness.assert_text_present("Moxfield (CSV)")
    harness.assert_text_present("Archidekt (CSV)")
    harness.assert_text_present("Deckbox (CSV)")

    # Verify batch metadata fields
    harness.assert_visible("#batch-name")
    harness.assert_visible("#product-type")
    harness.assert_visible("#batch-set-code")

    # Verify parse button
    harness.assert_visible("#parse-btn")

    # Verify info message
    harness.assert_text_present("Paste a CSV export or upload a file, then click Parse")

    harness.screenshot("final_state")
