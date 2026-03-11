"""
Hand-written implementation for order_status_toggle.

Toggles between Ordered and Owned status pills and verifies
the active state changes.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Verify Ordered is active by default
    harness.assert_visible(".pill[data-value='ordered'].active")

    # Click Owned pill
    harness.click_by_text("Owned")

    # Verify Owned is now active
    harness.assert_visible(".pill[data-value='owned'].active")

    # Click Ordered to switch back
    harness.click_by_text("Ordered")

    # Verify Ordered is active again
    harness.assert_visible(".pill[data-value='ordered'].active")

    harness.screenshot("final_state")
