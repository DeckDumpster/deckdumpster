"""
Hand-written implementation for card_detail_not_found.

Navigates to an invalid card URL and verifies the error state.
"""


def steps(harness):
    # start_page: /card/zzz/999 — auto-navigated by test runner.
    # Wait for error message.
    harness.wait_for_text("Card not found")
    harness.assert_text_present("Card not found")
    # Error is in the empty-state div.
    harness.assert_visible(".empty-state")
    # Site header should still be present.
    harness.assert_visible(".site-header")
    harness.screenshot("final_state")
