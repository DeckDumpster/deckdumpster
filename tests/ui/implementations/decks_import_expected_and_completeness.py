"""
Hand-written implementation for decks_import_expected_and_completeness.

Opens Bolt Tribal, imports an expected list with one card present
(Beast-Kin Ranger) and one missing but unassigned (Cathar Commando),
then verifies the completeness section shows both groups.
"""


def steps(harness):
    # Click "Bolt Tribal" deck to open detail view.
    harness.click_by_text("Bolt Tribal")
    harness.wait_for_visible("#detail-view.active", timeout=5_000)
    # Click "Import Expected List" to open the modal.
    harness.click_by_text("Import Expected List")
    harness.wait_for_visible("#expected-modal.active", timeout=5_000)
    # Paste a decklist: Beast-Kin Ranger is in the deck, Cathar Commando is not.
    harness.fill_by_selector(
        "#f-expected-list",
        "1 Beast-Kin Ranger (FDN) 100\n1 Cathar Commando (FDN) 139"
    )
    # Click "Import".
    harness.click_by_selector("#expected-modal button")
    # Wait for modal to close and completeness to load.
    harness.wait_for_hidden("#expected-modal.active", timeout=5_000)
    harness.wait_for_visible("#completeness-section", timeout=5_000)
    # Verify the completeness section shows present and missing cards.
    harness.assert_text_present("Present")
    harness.assert_text_present("Beast-Kin Ranger")
    harness.assert_text_present("Missing")
    harness.assert_text_present("Cathar Commando")
    harness.assert_text_present("Unassigned")
    harness.screenshot("final_state")
