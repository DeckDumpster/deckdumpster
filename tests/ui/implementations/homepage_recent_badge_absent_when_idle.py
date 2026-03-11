"""
Hand-written implementation for homepage_recent_badge_absent_when_idle.
Verifies that when no cards are in READY_FOR_OCR or PROCESSING state,
no processing badge appears next to the Recent link, and the link
is still navigable.
"""


def steps(harness):
    # Navigate to homepage
    harness.navigate("/")

    # Wait for page to fully load (settings pills become active)
    harness.wait_for_visible("#image-display-pills .pill.active")

    # Verify Recent link is visible
    harness.assert_text_present("Recent")

    # Verify no badge element exists (no READY_FOR_OCR or PROCESSING)
    harness.assert_hidden("#recent-badge-wrap .badge")

    # Verify the word "processing" does not appear on the page
    harness.assert_text_absent("processing")

    # Click Recent link to confirm it is navigable
    harness.click_by_selector("a[href='/recent']")
    harness.wait_for_text("Recent")

    harness.screenshot("final_state")
