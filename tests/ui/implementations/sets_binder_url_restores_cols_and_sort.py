"""
Hand-written implementation for sets_binder_url_restores_cols_and_sort.

Changes cards-per-row and sort, checks both land in the query string with the
defaults elided, then reloads that URL and checks the view comes back.
"""

from urllib.parse import urlparse


def steps(harness):
    # start_page: /sets/spg — auto-navigated by test runner.

    harness.wait_for_text("165 printings", timeout=5_000)

    # A fresh browser context per test means localStorage is empty, so this is
    # the default view and the URL should be carrying nothing.
    assert urlparse(harness.page.url).query == "", (
        f"Defaults leaked into the URL: {harness.page.url}"
    )
    assert harness.page.inner_text("#col-count").strip() == "6"

    harness.click_by_selector("#col-plus")
    harness.click_by_selector("#col-plus")
    harness.select_by_label("#sort", "Name")

    # Both handlers write the URL before starting the refetch, so this does not
    # wait on the fetch — only on the click and change events landing.
    harness.page.wait_for_timeout(300)
    changed = urlparse(harness.page.url)
    assert changed.query == "cols=8&sort=name", (
        f"Expected cols=8&sort=name in the URL, got {changed.query!r}"
    )

    # Reload that address and the same view comes back.
    harness.navigate(f"{changed.path}?{changed.query}")
    harness.wait_for_text("165 printings", timeout=5_000)

    assert harness.page.inner_text("#col-count").strip() == "8"
    assert harness.page.input_value("#sort") == "name"
    tracks = harness.page.evaluate(
        "getComputedStyle(document.querySelector('.card-grid'))"
        ".gridTemplateColumns.trim().split(/\\s+/).length"
    )
    assert tracks == 8, f"Restored grid is {tracks} wide, expected 8"

    harness.screenshot("final_state")
