"""
Implementation for deck_detail_list_view_no_overflow.

Navigates to a deck detail page in list view and verifies that the
type-grouped card columns fit within the viewport without overflow
at both desktop and mobile widths.
"""


def _assert_no_overflow(harness, label):
    overflow = harness.page.evaluate(
        "document.body.scrollWidth > document.body.clientWidth"
    )
    if overflow:
        scroll_w = harness.page.evaluate("document.body.scrollWidth")
        client_w = harness.page.evaluate("document.body.clientWidth")
        raise AssertionError(
            f"Horizontal overflow at {label}: scrollWidth={scroll_w} > clientWidth={client_w}"
        )


def steps(harness):
    # Force list view before navigating
    harness.page.evaluate("localStorage.setItem('deckDetailView', 'list')")

    # Navigate to deck detail page
    harness.navigate("/decks/1")

    # Wait for type groups to render
    harness.wait_for_visible("#type-groups")

    # Verify type groups are visible with card content
    harness.assert_visible("#type-groups .card-row")

    # Verify no horizontal overflow at desktop width
    _assert_no_overflow(harness, "desktop (1280px)")
    harness.screenshot("desktop")

    # Resize to mobile width and verify no overflow
    harness.page.set_viewport_size({"width": 390, "height": 844})
    harness.page.wait_for_timeout(500)
    _assert_no_overflow(harness, "mobile (390px)")
    harness.screenshot("final_state")
