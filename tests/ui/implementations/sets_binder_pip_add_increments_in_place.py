"""
Hand-written implementation for sets_binder_pip_add_increments_in_place.

Clicks the nonfoil pip on spg's one owned card and verifies the count moves
in place -- no reload, no modal -- while the completion meter stays put.
"""


def steps(harness):
    # start_page: /sets/spg?filter=have — auto-navigated by test runner.

    # filter=have leaves exactly one tile, so every selector below is
    # unambiguous without indexing.
    harness.wait_for_text("1 printing", timeout=5_000)
    harness.assert_element_count(".sheet-card", 1)

    # One copy held, so the pip shows the bare label; the count appears only
    # above one.
    assert harness.page.inner_text(".finish-pip").strip() == "NF"
    before = harness.page.inner_text("#meter-all-count").strip()
    assert before == "1 / 165", f"Unexpected starting meter: {before}"

    # A reload would clear this. Read back after the click, it is the proof
    # that the increment happened in the page rather than through a refetch.
    harness.page.evaluate("window.__binderNoReload = true")

    # One click on the nonfoil pip. No modal, no form.
    harness.click_by_selector(".finish-pip")

    # The optimistic increment paints before the POST returns; the wait is for
    # the request to finish so a server-side rejection would roll it back and
    # fail the next assertion rather than passing on the optimistic paint.
    harness.wait_for_text("NF 2", timeout=3_000)
    harness.assert_element_count(".pip-error", 0)
    harness.assert_hidden(".card-modal-overlay.active")

    assert harness.page.evaluate("window.__binderNoReload === true"), (
        "The page reloaded — the add is supposed to be in place"
    )

    # Both meters count printings, never copies: the pocket was already filled,
    # so a second copy fills nothing new.
    after = harness.page.inner_text("#meter-all-count").strip()
    assert after == before, f"Meter moved on a second copy: {before} -> {after}"

    harness.screenshot("final_state")
