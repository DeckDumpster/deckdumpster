"""
Hand-written implementation for sealed_disposed_entries_dimmed.

Verifies that checking the Opened filter shows opened entries with
dimmed/disposed visual treatment.
"""


def steps(harness):
    # Open filters sidebar
    harness.click_by_text("Filters")
    harness.wait_for_visible("#sidebar.open")

    # Check the Opened status filter via its label (checkbox itself is hidden)
    harness.click_by_selector("label[for='status-opened']")

    # Close sidebar via backdrop
    harness.click_by_selector("#sidebar-backdrop")
    harness.page.wait_for_timeout(500)

    # Verify the opened entry now appears with the .disposed class
    harness.assert_visible(".disposed")

    harness.screenshot("final_state")
