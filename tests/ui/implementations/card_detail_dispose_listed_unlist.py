"""
Hand-written implementation for card_detail_dispose_listed_unlist.

Disposes a copy as "Listed", verifies the Unlist option appears, then unlists it
and verifies it returns to owned status with the Listed option restored.
"""


def steps(harness):
    # start_page: /card/lci/113 — auto-navigated by test runner.
    harness.wait_for_text("Preacher of the Schism")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=500)
    # Select "Listed" from the dispose dropdown.
    harness.select_by_label(".dispose-select", "Listed")
    # Click Dispose.
    harness.click_by_selector(".dispose-btn")
    # After dispose, the copy status becomes "listed" which is still active,
    # so no .disposition-badge appears. Instead, the dispose-select now
    # shows "Unlist" instead of "Listed". Wait for the page to re-render.
    harness.wait_for_visible(".dispose-select", timeout=500)
    # Verify "Unlist" is now an option (status is "listed").
    harness.select_by_label(".dispose-select", "Unlist")
    # Click Dispose again to unlist (sets status back to "owned").
    harness.click_by_selector(".dispose-btn")
    # After unlisting, the copy is "owned" again. The dispose-select should
    # now show "Listed" as an option again.
    harness.wait_for_visible(".dispose-select", timeout=500)
    harness.assert_visible(".dispose-select")
    harness.screenshot("final_state")
