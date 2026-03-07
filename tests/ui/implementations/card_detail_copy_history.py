"""
Hand-written implementation for card_detail_copy_history.

Expands and collapses the history timeline on a copy.
BLB 124 (Artist's Talent) has an owned copy with at least an initial
status change in demo data.
"""


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    harness.wait_for_text("Artist's Talent")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=10_000)
    # Click the "History" toggle button.
    harness.click_by_selector(".history-toggle")
    # Timeline should appear.
    harness.wait_for_visible(".history-timeline", timeout=10_000)
    harness.assert_visible(".history-event")
    harness.screenshot("history_expanded")
    # Click again to collapse.
    harness.click_by_selector(".history-toggle")
    # Timeline should disappear.
    harness.wait_for_hidden(".history-timeline")
    harness.screenshot("final_state")
