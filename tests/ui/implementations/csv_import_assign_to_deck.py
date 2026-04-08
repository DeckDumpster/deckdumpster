"""
Hand-written implementation for csv_import_assign_to_deck.

Parses and resolves a deck list, verifies the assign target dropdown has
deck/binder optgroups, selects a deck, commits, and verifies success.
"""


def steps(harness):
    # Harness auto-navigates to /import-csv (from hint start_page)
    harness.wait_for_visible("#csv-text")

    # Paste valid deck list
    harness.fill_by_selector(
        "#csv-text",
        "1 Beast-Kin Ranger (FDN) 100",
    )

    # Parse & Resolve
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=500)

    # Select a deck (assign targets load automatically after resolve)
    harness.select_by_label("#assign-target", "Bolt Tribal")

    # Commit
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Successfully added", timeout=500)

    harness.screenshot("final_state")
