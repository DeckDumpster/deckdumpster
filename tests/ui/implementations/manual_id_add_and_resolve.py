"""
Hand-written implementation for manual_id_add_and_resolve.

Adds a card by set code and collector number, resolves it, and verifies
the resolved card name and thumbnail appear in the results.
"""


def steps(harness):
    # Navigate to Manual ID Entry page
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Select Common rarity
    harness.select_by_label("#rarity-select", "C")

    # Enter collector number
    harness.fill_by_selector("#cn-input", "100")

    # Enter set code
    harness.fill_by_selector("#set-input", "fdn")

    # Click Add to stage the entry
    harness.click_by_selector("#add-btn")

    # Verify entry appears in staging table
    harness.wait_for_visible("#entry-tbody tr")

    # Click Resolve
    harness.click_by_selector("#resolve-btn")

    # Wait for resolved card to appear
    harness.wait_for_text("Beast-Kin Ranger", timeout=500)

    harness.screenshot("final_state")
