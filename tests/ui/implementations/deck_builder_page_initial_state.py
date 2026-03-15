"""
Hand-written implementation for deck_builder_page_initial_state.

Verifies the deck builder create form renders with all expected elements.
"""


def steps(harness):
    # Navigate to the deck builder page
    harness.navigate("/deck-builder")
    # Verify the create form heading
    harness.wait_for_text("New Commander Deck")
    # Verify the Build nav link exists
    harness.assert_text_present("Build")
    # Verify the commander search input placeholder
    harness.assert_visible("#cmd-input")
    # Verify Physical radio option is present
    harness.assert_text_present("Physical")
    # Verify Hypothetical radio option is present
    harness.assert_text_present("Hypothetical")
    # Verify Create Deck button exists
    harness.assert_text_present("Create Deck")
    harness.screenshot("final_state")
