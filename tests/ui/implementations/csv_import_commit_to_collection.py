"""
Hand-written implementation for csv_import_commit_to_collection.

Parses and resolves a deck list, commits to collection, and verifies
the success message.
"""


def steps(harness):
    harness.navigate("/import-csv")
    harness.wait_for_visible("#csv-text")

    # Paste valid deck list
    harness.fill_by_selector(
        "#csv-text",
        "1 Beast-Kin Ranger (FDN) 100\n1 Cathar Commando (FDN) 139",
    )

    # Parse & Resolve
    harness.click_by_selector("#parse-btn")
    harness.wait_for_text("Resolved", timeout=10000)

    # Commit
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Successfully added", timeout=10000)

    harness.screenshot("final_state")
