"""
Hand-written implementation for deck_builder_create_and_view.

Creates a commander deck and verifies the builder layout renders correctly.
"""


def steps(harness):
    # Navigate to the deck builder page
    harness.navigate("/deck-builder")
    harness.wait_for_text("New Commander Deck")
    # Search for a commander
    harness.fill_by_placeholder("Search your collection...", "Bonny")
    harness.wait_for_text("Bonny Pall, Clearcutter", timeout=500)
    # Select the commander
    harness.click_by_text("Bonny Pall, Clearcutter")
    # Click Create Deck
    harness.click_by_text("Create Deck")
    # Wait for builder mode to render with commander name as deck title
    harness.wait_for_text("Bonny Pall, Clearcutter", timeout=500)
    # Verify the card count badge
    harness.assert_text_present("0/100")
    # Verify the Commander section exists
    harness.assert_text_present("Commander")
    # Verify the Add Card button
    harness.assert_text_present("+ Add Card")
    # Verify the card preview image loaded
    harness.assert_visible("#preview-img")
    harness.screenshot("final_state")
