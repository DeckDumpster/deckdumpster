"""
Hand-written implementation for sets_binder_dismiss_promos_by_pill.

The other half of de-epk: promos arrive by default, so the pill now dismisses a
section rather than revealing one that was held back. The meters deliberately
do not follow the dismissal -- they are computed before q/filter/sections and
describe the set, not the view.
"""

from urllib.parse import urlparse


def steps(harness):
    # start_page: /sets/mkm -- auto-navigated by test runner.
    harness.wait_for_text("440 printings", timeout=5_000)
    harness.assert_visible('.section[data-section="promo"]')

    harness.click_by_selector("#sections button[data-section='promo']")

    # The handler writes the URL before starting the refetch, so this waits on
    # the click landing rather than on the fetch -- the interaction budget is
    # about the click, and the restored view is checked on a fresh load below.
    harness.page.wait_for_timeout(300)
    dismissed = urlparse(harness.page.url)
    assert dismissed.query == "sections=base%2Cextended", (
        f"Dismissing promos wrote {dismissed.query!r} to the URL"
    )

    # The narrowed view is a link, and it comes back narrowed.
    harness.navigate(f"{dismissed.path}?{dismissed.query}")
    harness.wait_for_text("430 printings", timeout=5_000)

    harness.assert_element_count('.section[data-section="promo"]', 0)
    harness.assert_element_count(".sheet-card", 430)
    on = harness.page.eval_on_selector_all(
        "#sections button[data-section]",
        "els => els.filter(e => e.classList.contains('on'))"
        ".map(e => e.dataset.section)",
    )
    assert on == ["base", "extended"], f"Restored pills: {on}"

    # The meter still counts the set. 430 tiles under a 440 meter is the user's
    # own choice here, which is what makes the default view's agreement mean
    # something.
    total = harness.page.inner_text("#meter-all-count").split("/")[1].strip()
    assert total == "440", f"The meter followed the dismissal: {total}"

    harness.screenshot("final_state")
