"""
Hand-written implementation for collection_syntax_help_pill.

Verifies the new visible "? Syntax" pill in the collection header is
discoverable and points at /search-help. Replaces the previous tiny
inline "?" link that was hard to find and hard to tap on touch devices.
The destination page itself is covered by collection_search_help_page.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    harness.wait_for_visible("#search-input")

    # The pill is rendered as a bordered link, easy to spot.
    harness.assert_visible("a.syntax-help-link")
    harness.assert_text_present("Syntax")

    # Verify the pill links to the search help page in a new tab.
    harness.assert_visible(
        "a.syntax-help-link[href='/search-help'][target='_blank']"
    )

    harness.screenshot("final_state")
