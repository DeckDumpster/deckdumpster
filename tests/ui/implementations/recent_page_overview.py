"""
Hand-written implementation for recent_page_overview.

Views the Recent Images page and verifies ingest pipeline images appear
with status indicators.
"""


def steps(harness):
    # Navigate to Recent Images page
    harness.navigate("/recent")
    harness.wait_for_visible("#grid")

    # Verify image cards appear (demo ingest samples)
    harness.wait_for_visible(".img-card")

    # Verify summary shows image count
    harness.assert_visible("#summary")

    # Verify done status cards are present (green border)
    harness.assert_visible(".img-card.done")

    harness.screenshot("final_state")
