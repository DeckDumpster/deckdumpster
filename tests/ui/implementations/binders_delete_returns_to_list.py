"""
Hand-written implementation for binders_delete_returns_to_list.

Deletes the "Foil Collection" binder and verifies it disappears from
the list view.
"""


def steps(harness):
    # start_page: /binders — auto-navigated by test runner.
    harness.wait_for_text("Foil Collection")

    # Click into Foil Collection detail
    harness.click_by_text("Foil Collection")
    harness.wait_for_visible(".detail-view.active")

    # Click Delete Binder (confirm dialog auto-accepted)
    harness.click_by_text("Delete Binder")

    # Verify we return to list view
    harness.wait_for_visible(".list-view.active")

    # Verify only one binder card remains (the hidden detail-view h2
    # still contains "Foil Collection" text, so we count visible cards
    # instead of using assert_text_absent).
    harness.assert_element_count(".binder-card", 1)

    # Verify Trade Binder remains
    harness.assert_text_present("Trade Binder")

    harness.screenshot("final_state")
