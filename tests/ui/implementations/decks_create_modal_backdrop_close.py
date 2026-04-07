"""
Hand-written implementation for decks_create_modal_backdrop_close.

Opens the New Deck modal, clicks the backdrop to dismiss it, and verifies
the deck list is unchanged.
"""


def steps(harness):
    # start_page: /decks — auto-navigated by test runner.

    # Wait for deck grid to load
    harness.wait_for_text("Bolt Tribal")

    # Open the modal
    harness.click_by_text("New Deck")
    harness.wait_for_visible("#deck-modal.active")

    # Click the backdrop to close the modal.
    # The backdrop is the #deck-modal element itself (a full-viewport overlay).
    # Clicking the center would hit the inner .modal div, so we click at
    # position (10, 10) which is in the top-left corner of the backdrop,
    # outside the centered .modal content.
    harness.page.click("#deck-modal", position={"x": 10, "y": 10})

    # Verify the modal is no longer visible
    harness.wait_for_hidden("#deck-modal.active")

    # Verify the deck list is unchanged
    harness.assert_text_present("Bolt Tribal")
    harness.assert_text_present("Eldrazi Ramp")

    harness.screenshot("final_state")
