"""
Hand-written implementation for deck_share_button_copies_url.

Clicks the Share button on a deck page and verifies the button feedback.
"""


def steps(harness):
    # start_page from hints navigates to /decks/2

    # Wait for deck to load
    harness.wait_for_text("Eldrazi Ramp")

    # Grant clipboard permissions for headless browser
    harness.page.context.grant_permissions(["clipboard-read", "clipboard-write"])

    # Click the Share button
    harness.click_by_selector("#btn-share-deck")

    # Verify button text changes to "Copied!"
    harness.wait_for_text("Copied!", timeout=500)
    harness.assert_text_present("Copied!")

    harness.screenshot("final_state")
