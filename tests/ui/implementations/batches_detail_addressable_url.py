"""
Hand-written implementation for batches_detail_addressable_url.

Proves that /batches/:id is a real, bookmarkable detail page (not an
SPA modal). Direct-navigates to /batches/1, verifies the batch name,
type, deck assignment, and card grid all render from the pathname
parse alone.
"""


def steps(harness):
    # start_page: /batches/1 — auto-navigated by test runner.
    # The detail render is gated on the cards-grid appearing.
    harness.wait_for_visible(".cards-grid")

    # Heading is the batch name.
    harness.assert_text_present("Wednesday evening scan")

    # Type indicator comes from the info panel.
    harness.assert_text_present("Corner")

    # The assign-status branch (vs the assign form) is what we want:
    # this batch is already attached to a deck.
    harness.assert_visible(".assign-status")
    harness.assert_text_present("Bolt Tribal")
    harness.assert_text_present("sideboard")

    # At least one of the three cards is rendered in the grid.
    harness.assert_text_present("Condemn")

    # Back link exists to return to the list.
    harness.assert_visible("a[href='/batches']")

    harness.screenshot("final_state")
