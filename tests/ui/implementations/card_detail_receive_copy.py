"""
Hand-written implementation for card_detail_receive_copy.

Receives an ordered copy, transitioning it from "ordered" to "owned".
"""


def steps(harness):
    # start_page: /card/blb/188 — auto-navigated by test runner.
    harness.wait_for_text("Peerless Recycling")
    # Wait for copies to load.
    harness.wait_for_visible(".copy-section", timeout=10_000)
    # Verify "Receive" button is present (ordered status).
    harness.assert_visible(".receive-btn")
    harness.screenshot("before_receive")
    # Click the Receive button.
    harness.click_by_selector(".receive-btn")
    # After receiving, the copy section reloads. The Receive button disappears
    # and owned-status controls (dispose dropdown, deck/binder selects) appear.
    harness.wait_for_hidden(".receive-btn", timeout=10_000)
    harness.wait_for_visible(".dispose-select", timeout=10_000)
    harness.screenshot("final_state")
