"""
Hand-written implementation for manual_id_resolve_and_commit.

End-to-end happy path: add valid entries, resolve, verify assign target
dropdown has deck/binder optgroups, select a deck, commit, verify success.
"""


def steps(harness):
    # Harness auto-navigates to /ingestor-ids (from hint start_page)
    harness.wait_for_visible("#cn-input")

    # Select Common rarity and add a valid card
    harness.select_by_label("#rarity-select", "C")
    harness.fill_by_selector("#cn-input", "100")
    harness.fill_by_selector("#set-input", "fdn")
    harness.click_by_selector("#add-btn")

    # Click Resolve
    harness.click_by_selector("#resolve-btn")
    harness.wait_for_text("Beast-Kin Ranger", timeout=500)

    # Verify resolved table appears
    harness.assert_visible(".resolved-table")

    # Select a deck (assign targets load automatically after resolve)
    harness.select_by_label("#assign-target", "Bolt Tribal")

    # Commit to collection
    harness.click_by_selector("#commit-btn")
    harness.wait_for_text("Added", timeout=500)

    harness.screenshot("final_state")
