"""
Hand-written implementation for collection_unowned_scroll_reaches_end.

Scrolling to the bottom of a 7,603-row result must reach the last row, which
lives in a page the first response never contained.
"""


def steps(harness):
    harness.navigate("/collection?q=is%3Aunowned")
    harness.wait_for_visible("#vtbody tr[data-idx]:not([data-pending])", timeout=15_000)
    status_before = harness.page.inner_text("#status")

    # Jump past everything the first page held.
    harness.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    # The last row is only reachable if its page was fetched on the way. Wait
    # for a real row at the final index — placeholders do not count.
    harness.page.wait_for_function(
        """() => {
             const rows = [...document.querySelectorAll('#vtbody tr[data-idx]:not([data-pending])')];
             return rows.length && Math.max(...rows.map(r => +r.dataset.idx)) === totalMatches - 1;
           }""",
        timeout=25_000,
    )

    # That last row is real content, not an empty shell.
    last_text = harness.page.evaluate(
        """() => {
             const rows = [...document.querySelectorAll('#vtbody tr[data-idx]:not([data-pending])')];
             const last = rows.sort((a, b) => +a.dataset.idx - +b.dataset.idx).pop();
             return last ? last.innerText.trim() : '';
           }"""
    )
    assert last_text, "the final row rendered without any content"

    # Pages replaced the window rather than piling up in it.
    rendered = harness.page.eval_on_selector_all("#vtbody tr[data-idx]", "els => els.length")
    assert 0 < rendered < 200, f"expected the window to stay bounded, got {rendered} rows"

    # The count described the whole result from the first paint, so scrolling
    # gave it nothing to correct.
    assert harness.page.inner_text("#status") == status_before, (
        f"status drifted while scrolling: {status_before!r} -> {harness.page.inner_text('#status')!r}"
    )

    harness.screenshot("final_state")
