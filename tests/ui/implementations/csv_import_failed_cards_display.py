"""
Hand-written implementation for csv_import_failed_cards_display.

Pastes a mix of valid and fake card names, verifies both failed and
resolved card groups appear with appropriate styling.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Paste mixed valid and invalid deck list
    harness.fill_by_selector(
        "#csv-text",
        "1 Nonexistent Card XYZ (ZZZ) 999\n1 Beast-Kin Ranger (FDN) 100",
    )

    # Parse & Resolve
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Failed", timeout=500)

    # Verify failed count in summary bar
    harness.assert_text_present("Failed")

    # Verify resolved card still appears
    harness.assert_text_present("Beast-Kin Ranger")

    # Verify failed card group is visible
    harness.assert_visible(".unresolved")

    harness.screenshot("final_state")
