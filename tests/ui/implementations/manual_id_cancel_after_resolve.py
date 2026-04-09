"""
Hand-written implementation for manual_id_cancel_after_resolve.

Resolves a card entry, then clicks Cancel and verifies the cancellation message.
"""


def steps(harness):
    harness.navigate("/ingestor-ids")
    harness.wait_for_visible("#cn-input")

    # Add a valid entry
    harness.fill_by_selector("#cn-input", "100")
    harness.fill_by_selector("#set-input", "fdn")
    harness.click_by_selector("#add-btn")

    # Resolve
    harness.click_by_selector("#resolve-btn")
    harness.wait_for_text("Beast-Kin Ranger", timeout=500)

    # Click Cancel
    harness.click_by_selector("#cancel-btn")

    # Verify cancellation message
    harness.assert_text_present("Cancelled. Add more cards to start over.")

    harness.screenshot("final_state")
