"""
Hand-written implementation for collection_header_sticky_on_scroll.

Verifies position: sticky on the collection header holds after the
user scrolls the card list. Reads window.scrollY + header bounding
rect via page.evaluate to prove both that we actually scrolled and
that the header stayed pinned at the top of the viewport.
"""


def steps(harness):
    # start_page: /collection — auto-navigated by test runner.
    harness.wait_for_visible("#search-input")
    # Wait for the table body to populate so scrolling has somewhere to go.
    harness.wait_for_visible(".layout #main")

    # Scroll down several times to drive scrollY meaningfully positive.
    # harness.scroll("down") uses mouse wheel delta 500.
    for _ in range(5):
        harness.scroll("down")

    # Read scroll position and header bounding rect from the live page.
    state = harness.page.evaluate("""() => {
      const header = document.querySelector('header');
      const rect = header.getBoundingClientRect();
      return { scrollY: window.scrollY, headerTop: rect.top, headerVisible: rect.bottom > 0 };
    }""")
    assert state["scrollY"] > 100, (
        f"Expected window.scrollY > 100 after scrolling, got {state['scrollY']}. "
        f"If this is 0 the test didn't actually scroll and the sticky assertion is meaningless."
    )
    assert abs(state["headerTop"]) < 2, (
        f"Expected sticky header to stay pinned at top (y=0), got headerTop={state['headerTop']}. "
        f"The header has scrolled off with the rest of the page — position: sticky is broken."
    )
    assert state["headerVisible"], "Header bounding rect has zero height — something is very wrong."

    # Sanity: key header elements are still visible to the user after scroll.
    harness.assert_visible("a.brand-logo")
    harness.assert_visible("#search-input")
    harness.assert_visible("a.syntax-help-btn")

    harness.screenshot("final_state")
