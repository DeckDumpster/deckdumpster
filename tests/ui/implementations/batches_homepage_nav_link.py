"""
Hand-written implementation for batches_homepage_nav_link.

Navigates from the homepage to the Batches page via the nav link.
"""


def steps(harness):
    # Start on the homepage
    harness.navigate("/")
    # Verify the Batches nav link is visible
    harness.assert_text_present("Batches")
    # Click the Batches nav link
    harness.click_by_text("Batches")
    # Wait for the batches page to load with demo data
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")
    harness.screenshot("final_state")
