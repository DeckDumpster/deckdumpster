"""
Hand-written implementation for recent_column_adjust.

Tests the column count plus/minus controls on the Recent Images page.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")

    # Verify column controls are visible
    harness.assert_visible("#col-minus")
    harness.assert_visible("#col-plus")
    harness.assert_visible("#col-count")

    # Click plus to increase column count
    harness.click_by_selector("#col-plus")
    harness.screenshot("after_plus")

    # Click minus to decrease column count
    harness.click_by_selector("#col-minus")
    harness.click_by_selector("#col-minus")
    harness.screenshot("after_minus")

    harness.screenshot("final_state")
