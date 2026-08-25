"""
Hand-written implementation for sets_binder_promos_are_in_the_default_view.

de-epk: the header counted every printing in the set while the grid asked the
endpoint for `base,extended`, so the two disagreed by exactly the promos --
`hob` reported 321 printings and drew 320. Every section is a default now, so
the meter, the status line and the tiles on the page are one number.
"""

from urllib.parse import urlparse


def steps(harness):
    # start_page: /sets/mkm -- auto-navigated by test runner.
    harness.wait_for_text("440 printings", timeout=5_000)

    # Nothing was clicked to get here: promos are a default, not a request.
    assert urlparse(harness.page.url).query == "", (
        f"The default view named a section in the URL: {harness.page.url}"
    )
    on = harness.page.eval_on_selector_all(
        "#sections button[data-section]",
        "els => els.filter(e => e.classList.contains('on'))"
        ".map(e => e.dataset.section)",
    )
    assert on == ["base", "extended", "promo"], f"Pills on by default: {on}"

    # The promos are a section of their own, below the base set.
    harness.assert_visible('.section[data-section="promo"]')
    harness.assert_element_count('.section[data-section="promo"] .sheet-card', 10)

    # The reconciliation. The meter is counted before q/filter/sections, so
    # agreeing with the grid is a statement about the default view, not an
    # arithmetic identity. Only the denominator is the set; the owned side is
    # demo data and not what this scenario is about.
    total = harness.page.inner_text("#meter-all-count").split("/")[1].strip()
    assert total == "440", f"All-printings meter counts {total}, expected 440"
    harness.assert_element_count(".sheet-card", 440)

    harness.screenshot("final_state")
