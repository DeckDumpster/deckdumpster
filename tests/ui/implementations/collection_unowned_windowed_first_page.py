"""
Hand-written implementation for collection_unowned_windowed_first_page.

A 7,603-row result must paint as one bounded window: the count describes the
whole result while the DOM holds only what fits on screen.
"""


def steps(harness):
    harness.navigate("/collection?q=is%3Aunowned")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)

    # The count describes the whole result, not the page that was fetched.
    harness.assert_text_present("7,603 results")

    # ...while the DOM holds only a windowful. A page fetched whole would put
    # thousands of rows here; the bound is generous so a viewport change
    # cannot make this flap.
    rendered = harness.page.eval_on_selector_all("#vtbody tr[data-idx]", "els => els.length")
    assert 0 < rendered < 200, f"expected a bounded window of rows, got {rendered} in the DOM"

    # The scrollbar still spans the whole result: the bottom spacer reserves
    # the height of every row that has not been fetched.
    spacer = harness.page.eval_on_selector(
        "#vscroll-bottom td", "el => parseInt(el.style.height) || 0"
    )
    assert spacer > 100_000, f"expected the spacer to reserve the whole result, got {spacer}px"

    harness.screenshot("final_state")
