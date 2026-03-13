"""
Hand-written implementation for collection_unowned_status_dual_value.

Enables unowned mode with a set filter and verifies the status text shows
both owned and total dollar values.
"""


def steps(harness):
    # Navigate with set filter and unowned mode pre-applied via URL
    harness.navigate("/collection?sets=fdn&unowned=base")
    harness.wait_for_visible("#status")

    # Wait for the unowned data to load (shows "owned" and "missing" counts)
    harness.wait_for_text("missing (base)")

    # Verify dual value format in status text
    harness.assert_text_present("owned /")
    harness.assert_text_present("total")

    # Screenshot shows status bar with "X owned, Y missing (base) — $X owned / $Y total"
    harness.screenshot("final_state")
