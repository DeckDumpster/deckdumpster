"""
Hand-written implementation for collection_stats_modal_shows_breakdown.

Opens the result-stats modal from the inline result count and verifies
that counts, both price source blocks, and the rarity breakdown all
render. Then closes the modal via the X button.
"""


def steps(harness):
    harness.navigate("/collection")
    harness.wait_for_visible(".collection-table", timeout=15_000)

    # Wait for the inline result count to render its new short format
    harness.wait_for_text("45 cards")
    harness.screenshot("status_inline")

    # Click the result-count text to open the stats modal
    harness.click_by_selector("#status")
    harness.wait_for_visible("#stats-modal-overlay.active", timeout=5_000)

    # Modal heading + each section is present
    harness.assert_text_present("Result statistics")
    harness.assert_text_present("Entries (rows)")
    harness.assert_text_present("Cards (with quantity)")
    harness.assert_text_present("Distinct printings")
    harness.assert_text_present("Distinct cards")
    harness.assert_text_present("TCGplayer")
    harness.assert_text_present("Card Kingdom")
    harness.assert_text_present("By rarity")

    # Counts reflect the unfiltered fixture (43 entries / 45 cards)
    harness.assert_text_present("43")
    harness.assert_text_present("45")

    harness.screenshot("modal_open")

    # Close the modal via the X button
    harness.click_by_selector("#stats-modal-close")
    harness.wait_for_hidden("#stats-modal-overlay.active")

    harness.screenshot("final_state")
