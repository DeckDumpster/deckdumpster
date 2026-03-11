"""
Hand-written implementation for batches_already_assigned_view.

Verifies that an already-assigned batch shows status text instead of assignment controls.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    harness.wait_for_text("Wednesday evening scan")

    # Click on the assigned batch
    harness.click_by_text("Wednesday evening scan")

    # Wait for detail view to load
    harness.wait_for_text("Assigned to:")

    # Verify the assigned status is shown
    harness.assert_text_present("Bolt Tribal")
    harness.assert_text_present("sideboard")

    # Verify no assignment dropdown is present
    harness.assert_hidden("#assign-deck-select")

    harness.screenshot("final_state")
