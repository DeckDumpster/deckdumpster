"""
Hand-written implementation for collection_syntax_help_pill.

Verifies the red-outlined "?" syntax-help button next to the search
input is discoverable and points at /search-help. The destination page
itself is covered by collection_search_help_page.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    harness.wait_for_visible("#search-input")

    # The "?" button is rendered as a bordered link, easy to spot.
    harness.assert_visible("a.syntax-help-btn")

    # Verify the button links to the search help page in a new tab.
    harness.assert_visible(
        "a.syntax-help-btn[href='/search-help'][target='_blank']"
    )

    harness.screenshot("final_state")
