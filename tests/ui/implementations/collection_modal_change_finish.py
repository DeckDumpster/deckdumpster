"""
Hand-written implementation for collection_modal_change_finish.

Opens a card modal from the collection page, switches the copy's
finish from nonfoil to foil via the inline select, and verifies the
modal refreshes in place — the new finish appears in the copy header
without navigating away.
"""


def steps(harness):
    # start_page: /collection
    harness.wait_for_visible(".card-cell", timeout=5_000)
    # Filter down to the target card so click_by_text is unambiguous.
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "Beast-Kin")
    harness.press_key("Enter")
    harness.wait_for_text("Beast-Kin Ranger", timeout=5_000)
    harness.click_by_text("Beast-Kin Ranger")
    # Modal opens and loads copies asynchronously.
    harness.wait_for_visible("#card-modal-overlay")
    harness.wait_for_visible("#copies-container .copy-section", timeout=5_000)
    harness.assert_text_present("Nonfoil Near Mint")
    harness.screenshot("modal_open_nonfoil")
    # Flip finish to foil — handler PUTs /api/collection/3, then
    # loadModalCopies(card) + fetchCollection() refresh in place.
    harness.select_by_label(".change-finish-select", "Foil")
    # The same modal should now show the updated copy header.
    harness.wait_for_text("Foil Near Mint", timeout=5_000)
    harness.assert_visible("#card-modal-overlay")
    harness.assert_text_absent("Nonfoil Near Mint")
    harness.screenshot("final_state")
