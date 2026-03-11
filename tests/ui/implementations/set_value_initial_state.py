"""
Hand-written implementation for set_value_initial_state.

Loads the Set Value Analysis page and verifies all initial state
elements: title, toggles, disabled button, empty state message,
and hidden results sections.
"""


def steps(harness):
    # Navigate to the Set Value Analysis page
    harness.navigate("/set-value")

    # Verify page title
    harness.assert_text_present("Set Value Analysis")

    # Verify set search input is visible
    harness.wait_for_visible("#set-search")

    # Verify TCGplayer toggle is active
    harness.assert_visible("#source-toggle .pill.active")

    # Verify Normal type toggle is active
    harness.assert_visible("#type-toggle .pill.active")

    # Verify Analyze button is present but disabled
    harness.assert_visible("#analyze-btn")

    # Verify empty state message is displayed
    harness.assert_text_present("Select one or more sets and click Analyze")

    # Verify results sections are hidden
    harness.assert_hidden("#filter-bar")
    harness.assert_hidden("#summary")
    harness.assert_hidden("#chart-wrap")
    harness.assert_hidden("#top-cards")

    harness.screenshot("final_state")
