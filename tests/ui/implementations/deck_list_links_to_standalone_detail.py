"""
Hand-written implementation for deck_list_links_to_standalone_detail.

Navigates to the deck list page, clicks a deck card, and verifies
it navigates to the unified deck page.
"""


def steps(harness):
    # Navigate to deck list page
    harness.navigate("/decks")

    # Wait for deck grid to load
    harness.wait_for_text("Bolt Tribal")

    # Click the Bolt Tribal deck card (it's an <a> tag)
    harness.click_by_text("Bolt Tribal")

    # Wait for unified deck page to load
    harness.wait_for_visible(".deck-header h2")

    # Verify we're on the deck page
    harness.assert_text_present("Bolt Tribal")

    # Verify zone tabs are visible (confirms it's the unified page)
    harness.assert_text_present("Mainboard")
    harness.assert_text_present("Sideboard")

    # Verify view toggle is present
    harness.assert_visible("#view-list-btn")
    harness.assert_visible("#view-grid-btn")

    harness.screenshot("final_state")
