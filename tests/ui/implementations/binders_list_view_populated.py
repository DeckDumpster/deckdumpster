"""
Hand-written implementation for binders_list_view_populated.

Verifies the binder list view renders both binders with metadata,
then clicks into a binder detail view.
"""


def steps(harness):
    # Navigate to the Binders page
    harness.navigate("/binders")
    harness.wait_for_text("Trade Binder")

    # Verify both binders are present
    harness.assert_text_present("Foil Collection")

    # Verify card counts
    harness.assert_text_present("6 cards")

    # Verify metadata
    harness.assert_text_present("9-pocket")

    harness.screenshot("list_view")

    # Click into Trade Binder detail
    harness.click_by_text("Trade Binder")

    # Verify detail view loads
    harness.wait_for_visible("#binder-name")
    harness.assert_text_present("Trade Binder")
    harness.assert_text_present("blue")

    harness.screenshot("final_state")
