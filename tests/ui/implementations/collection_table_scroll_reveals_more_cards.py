"""
Hand-written implementation for collection_table_scroll_reveals_more_cards.

Scrolls the collection table and verifies that different cards appear,
confirming virtual scroll updates rendered rows on scroll.
"""


def steps(harness):
    # Navigate to collection page
    harness.navigate("/collection")
    harness.wait_for_visible("#vtbody tr[data-idx]", timeout=5_000)

    # Capture the first card name before scrolling
    first_card = harness.page.evaluate(
        "document.querySelector('#vtbody tr[data-idx] .card-name')?.textContent"
    )
    harness.screenshot("before_scroll")

    # Scroll to the bottom of the page
    harness.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    harness.page.wait_for_timeout(500)

    # Verify the visible cards changed after scrolling
    new_first_card = harness.page.evaluate(
        "document.querySelector('#vtbody tr[data-idx] .card-name')?.textContent"
    )
    assert new_first_card != first_card, (
        f"Expected different cards after scroll, but still showing '{first_card}'"
    )

    harness.screenshot("final_state")
