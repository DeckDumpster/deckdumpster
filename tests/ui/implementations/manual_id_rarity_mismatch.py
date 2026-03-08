"""
Hand-written implementation for manual_id_rarity_mismatch.

Adds a card with an incorrect rarity selection, resolves it, and verifies
a rarity mismatch warning appears in the results.
"""


def steps(harness):
    # Navigate to Manual ID Entry page
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Select Rare rarity (card is actually Common)
    harness.select_by_label("#rarity-select", "R")

    # Enter collector number for Beast-Kin Ranger (Common)
    harness.fill_by_selector("#cn-input", "100")

    # Enter set code
    harness.fill_by_selector("#set-input", "fdn")

    # Click Add
    harness.click_by_selector("#add-btn")

    # Click Resolve
    harness.click_by_selector("#resolve-btn")

    # Wait for resolved card
    harness.wait_for_text("Beast-Kin Ranger", timeout=10000)

    # Verify rarity mismatch warning
    harness.assert_text_present("Expected")

    harness.screenshot("final_state")
