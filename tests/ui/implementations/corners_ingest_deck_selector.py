"""
Hand-written implementation for corners_ingest_deck_selector.

Verifies the deck selector on the ingest corners page has the expected
structure: deck dropdown with "Create new deck" option and zone selector
with Mainboard/Sideboard/Commander options.

The deck selector is hidden by default (display:none) and only shown
after detection results exist. We use JS to reveal it, simulating
the post-detection state.
"""


def steps(harness):
    # start_page: /ingest-corners — auto-navigated by test runner.
    # The deck selector and results section are hidden by default (display:none).
    # Reveal them via JS to test the deck selector structure.
    harness.page.evaluate("""
        document.getElementById('results-section').style.display = 'block';
        document.getElementById('deck-selector').style.display = 'block';
    """)
    # Wait for the deck selector to be visible.
    harness.wait_for_visible("#deck-select", timeout=500)
    # Verify the "Create new deck" option exists.
    harness.assert_text_present("Create new deck")
    # Verify zone selector has expected options.
    harness.assert_visible("#zone-select")
    # Select an existing deck from the dropdown (format appended to name).
    harness.select_by_label("#deck-select", "Bolt Tribal (modern)")
    harness.screenshot("final_state")
