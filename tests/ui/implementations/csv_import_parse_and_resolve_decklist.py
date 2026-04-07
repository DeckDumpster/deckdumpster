"""
Hand-written implementation for csv_import_parse_and_resolve_decklist.

Pastes a plain text deck list, parses and resolves it, and verifies
the resolved cards table and action bar appear.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Paste a deck list with set codes and collector numbers
    harness.fill_by_selector(
        "#csv-text",
        "1 Beast-Kin Ranger (FDN) 100\n1 Cathar Commando (FDN) 139",
    )

    # Click Parse & Resolve
    harness.click_by_selector("#parse-btn")

    # Wait for resolved results
    harness.wait_for_text("Resolved", timeout=500)

    # Verify summary bar
    harness.assert_visible(".summary-bar")

    # Verify resolved cards in table
    harness.assert_text_present("Beast-Kin Ranger")
    harness.assert_text_present("Cathar Commando")

    # Verify action bar with commit and cancel buttons
    harness.assert_visible("#commit-btn")
    harness.assert_visible("#cancel-btn")

    harness.screenshot("final_state")
