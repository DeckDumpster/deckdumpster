"""
Hand-written implementation for order_page_initial_state.

Verifies the Order Ingestion page loads with correct initial state:
textarea, drop zone, status pills, format dropdown, info message, Home link.
"""


def steps(harness):
    harness.navigate("/ingestor-order")
    harness.wait_for_visible("#order-text")

    # Verify textarea is present
    harness.assert_visible("#order-text")

    # Verify file drop zone
    harness.assert_visible("#file-drop")
    harness.assert_text_present("Click or drop .html / .txt files")

    # Verify status pills -- Ordered active by default
    harness.assert_visible(".pill.active")
    harness.assert_text_present("Ordered")
    harness.assert_text_present("Owned")

    # Verify format dropdown
    harness.assert_visible("#format-select")
    harness.assert_text_present("Auto-detect")

    # Verify info message in results
    harness.assert_text_present("Paste order data or upload files, then click Parse.")

    # Verify Home link
    harness.assert_visible("header a[href='/']")

    harness.screenshot("final_state")
