"""
Hand-written implementation for batches_detail_back_preserves_filter.

Verifies that the filter pill state is preserved after navigating into
a batch detail and clicking Back.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    harness.wait_for_text("Wednesday evening scan")

    # Click the "Corner" filter pill
    harness.click_by_selector("[data-type='corner']")

    # Verify batches are still visible (both are corner type)
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")

    # Enter a batch detail
    harness.click_by_text("Wednesday evening scan")
    harness.wait_for_text("Assigned to:")

    # Click Back to return to list
    harness.click_by_text("Back")

    # Verify the list reappears with batches visible
    harness.wait_for_text("Wednesday evening scan")
    harness.assert_text_present("New cards from LGS")

    # Verify the Corner pill is still active (via screenshot - Claude Vision will see it)
    harness.screenshot("final_state")
