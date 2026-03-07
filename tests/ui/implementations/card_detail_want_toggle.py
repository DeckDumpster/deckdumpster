"""
Hand-written implementation for card_detail_want_toggle.

Toggles the wishlist button on and off, verifying state changes.
"""


def steps(harness):
    # start_page: /card/blb/124 — auto-navigated by test runner.
    harness.wait_for_text("Artist's Talent")
    # Click "Want" to add to wishlist.
    harness.click_by_selector("#want-btn")
    # Button should change to "Wanted" with .wanted class.
    harness.wait_for_text("Wanted")
    harness.assert_visible("#want-btn.wanted")
    harness.screenshot("wanted_state")
    # Click again to remove from wishlist.
    harness.click_by_selector("#want-btn")
    # Button should revert to "Want" without .wanted class.
    harness.wait_for_hidden("#want-btn.wanted")
    harness.assert_text_present("Want")
    harness.screenshot("final_state")
