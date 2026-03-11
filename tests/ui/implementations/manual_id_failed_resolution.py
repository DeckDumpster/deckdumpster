"""
Hand-written implementation for manual_id_failed_resolution.

Adds entries with invalid set/CN, resolves, verifies failed section appears,
then uses Edit & Retry to move the entry back to staging.
"""


def steps(harness):
    # Harness auto-navigates to /ingestor-ids (from hint start_page)
    harness.wait_for_visible("#cn-input")

    # Add an entry with invalid set code and collector number
    harness.fill_by_selector("#cn-input", "9999")
    harness.fill_by_selector("#set-input", "zzz")
    harness.click_by_selector("#add-btn")

    # Click Resolve
    harness.click_by_selector("#resolve-btn")

    # Wait for failed results
    harness.wait_for_text("Failed", timeout=10000)

    # Verify failed section appears
    harness.assert_visible(".failed-section")

    # Click Edit & Retry to move entry back to staging
    harness.click_by_selector(".retry-btn")
    harness.wait_for_visible("#entry-tbody tr")

    harness.screenshot("final_state")
