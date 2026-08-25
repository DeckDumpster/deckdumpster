"""
Hand-written implementation for sets_binder_breadcrumb_back_to_the_set_list.

Clicks the breadcrumb on one set's binder page and checks it lands on the set
list — the page, not just the address.
"""

from urllib.parse import urlparse


def steps(harness):
    # start_page: /sets/spg — auto-navigated by test runner.

    # Settle the binder page first, so the click lands on a finished page
    # rather than mid-fetch.
    harness.wait_for_text("165 printings", timeout=5_000)
    harness.assert_visible(".breadcrumb a")

    # By selector, not by text: "All sets" is a prefix of both "All pockets"
    # (the filter select) and "All printings" (the completion meter), and
    # click_by_text takes the first match in document order.
    harness.click_by_selector(".breadcrumb a")

    # The set list's own furniture — a link that changes the URL and renders
    # nothing is the failure this is here to catch.
    harness.wait_for_visible("#set-filter", timeout=5_000)
    harness.wait_for_visible("#sets-rail", timeout=5_000)

    landed = urlparse(harness.page.url)
    assert landed.path == "/sets", f"Breadcrumb landed on {harness.page.url}"

    harness.screenshot("final_state")
