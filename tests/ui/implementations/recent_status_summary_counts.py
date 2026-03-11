"""
Hand-written implementation for recent_status_summary_counts.

Verifies the summary line shows correct status counts for fixture data.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")
    harness.wait_for_visible("#summary")

    # Verify summary shows the expected counts from fixture
    harness.assert_text_present("4 image(s)")
    harness.assert_text_present("2 done")
    harness.assert_text_present("2 error")

    harness.screenshot("final_state")
