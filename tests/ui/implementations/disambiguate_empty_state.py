"""
Hand-written implementation for disambiguate_empty_state.

Verifies the empty state message when no cards need disambiguation.
"""


def steps(harness):
    # Navigate to Disambiguate page
    harness.navigate("/disambiguate")

    # Verify empty state message appears
    harness.wait_for_visible("#empty-state")
    harness.assert_text_present("No cards")

    harness.screenshot("final_state")
