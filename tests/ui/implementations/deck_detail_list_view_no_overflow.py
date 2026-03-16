"""
Implementation for deck_detail_list_view_no_overflow.

Navigates to a deck detail page in list view and verifies that the
type-grouped card columns fit within the viewport without overflow.
"""


def steps(harness):
    # Force list view before navigating
    harness.page.evaluate("localStorage.setItem('deckDetailView', 'list')")

    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for type groups to render
    harness.wait_for_visible("#type-groups")

    # Verify type groups are visible with card content
    harness.assert_visible("#type-groups .card-row")

    # Verify no horizontal overflow on the page
    overflow = harness.page.evaluate(
        "document.body.scrollWidth > document.body.clientWidth"
    )
    if overflow:
        scroll_w = harness.page.evaluate("document.body.scrollWidth")
        client_w = harness.page.evaluate("document.body.clientWidth")
        raise AssertionError(
            f"Horizontal overflow detected: scrollWidth={scroll_w} > clientWidth={client_w}"
        )

    harness.screenshot("final_state")
