"""
Hand-written implementation for sealed_default_filter_hides_opened.

Verifies the sealed page hides disposed entries by default and only
shows owned/listed items.
"""


def steps(harness):
    # The fixture has 6 owned + 1 listed + 1 opened = 8 total
    # Default filter should show only 7 (owned + listed)
    harness.assert_text_present("7 entries")

    # Open the filters sidebar to check status pills
    harness.click_by_text("Filters")
    harness.wait_for_visible("#sidebar.open")

    # Verify Owned and Listed are checked, Opened is not
    assert harness.page.is_checked("#status-owned"), "Owned should be checked"
    assert harness.page.is_checked("#status-listed"), "Listed should be checked"
    assert not harness.page.is_checked("#status-opened"), "Opened should not be checked"

    harness.screenshot("final_state")
