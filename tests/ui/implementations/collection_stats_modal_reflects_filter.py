"""
Hand-written implementation for collection_stats_modal_reflects_filter.

Filters the collection with rarity:rare, then opens the stats modal and
verifies the counts reflect the filtered subset (13 entries / 15 cards),
not the unfiltered fixture (43 entries / 45 cards).
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)

    # Confirm we start on the unfiltered total
    harness.wait_for_text("45 cards")

    # Narrow to rares (13 entries with combined qty=15 in the fixture)
    harness.fill_by_placeholder("Search (e.g. t:creature c:r mv>=3)", "rarity:rare")
    harness.wait_for_text("15 cards")
    harness.screenshot("filtered_status")

    # Open the stats modal
    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=5_000)

    # Modal counts must match the filtered subset, not the full collection
    harness.assert_text_present("Entries (rows)")
    harness.assert_text_present("13")
    harness.assert_text_present("15")

    # The "By rarity" pills should only show "rare" — the unfiltered modal
    # would show common/uncommon/mythic too. Their absence inside the modal
    # proves the filter was applied.
    harness.assert_visible("#stats-modal-overlay.active .stats-rarity-pill")
    harness.assert_element_count("#stats-modal-overlay.active .stats-rarity-pill", 1)

    harness.screenshot("final_state")
