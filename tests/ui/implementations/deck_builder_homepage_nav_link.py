"""
Hand-written implementation for deck_builder_homepage_nav_link.

Navigates from the homepage to the Deck Builder page via the nav link.
"""


def steps(harness):
    # Start on the homepage
    harness.navigate("/")
    # Verify the Deck Builder nav link is visible
    harness.assert_text_present("Deck Builder")
    # Click the Deck Builder nav link
    harness.click_by_text("Deck Builder")
    # Wait for the deck builder page to load
    harness.wait_for_text("New Commander Deck")
    # Verify the create form rendered
    harness.assert_text_present("Create Deck")
    harness.screenshot("final_state")
