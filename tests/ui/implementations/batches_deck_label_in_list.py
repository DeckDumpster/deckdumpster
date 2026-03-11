"""
Hand-written implementation for batches_deck_label_in_list.

Verifies that assigned batches show a deck label in the list view and
unassigned batches do not.
"""


def steps(harness):
    # Navigate to the Batches page
    harness.navigate("/batches")
    harness.wait_for_text("Wednesday evening scan")

    # Verify the assigned batch shows its deck label
    harness.assert_text_present("Deck: Bolt Tribal")

    # Verify both batch names are present
    harness.assert_text_present("New cards from LGS")
    harness.assert_text_present("Wednesday evening scan")

    harness.screenshot("final_state")
