"""The /sets/:set_code binder grid page is served, and its assets exist.

The page is one static file whose behaviour lives in the browser, so what is
checkable over HTTP is the wiring: the route serves it for any set code, and
every asset it names comes back.  A page that 404s a script tag renders an
empty grid and looks like an empty set, which is the failure this guards.

The grid's behaviour -- pips, meters, URL round-trip -- is covered by the UI
scenarios under tests/ui/.

Usage:
    uv run pytest tests/integration/test_set_browse_page.py -v --instance <instance>
"""

import re

import pytest

#: Every asset the page pulls in. Listed here rather than scraped so a dropped
#: <script> tag fails a test instead of silently shrinking the check.
PAGE_ASSETS = (
    "/static/shared.js",
    "/static/shared-card-table.js",
    "/static/shared-card-tile.js",
    "/static/shared-card-modal.js",
    "/static/shared-card-tile.css",
    "/static/shared-card-modal.css",
    "/static/vendor/keyrune/keyrune.min.css",
)


@pytest.fixture(scope="module")
def cached_set(api):
    status, sets = api.get("/api/cached-sets")
    assert status == 200, sets
    if not sets:
        pytest.skip("no cached sets on this instance")
    return sets[0]["code"]


def _page(api, path):
    status, body = api.get_raw(path)
    assert status == 200, f"{path} -> {status}"
    return body.decode()


def test_the_route_serves_the_binder_page(api, cached_set):
    html = _page(api, f"/sets/{cached_set}")

    assert "<title>Browse Set</title>" in html
    assert 'id="content"' in html


def test_an_uncached_set_still_gets_the_page(api):
    """The 404 for an unknown set belongs to the API, not the route.

    The page reads its own set code out of the path and renders the endpoint's
    error; serving a 404 here instead would replace that message with the
    server's bare not-found body.
    """
    html = _page(api, "/sets/zzz")

    assert "<title>Browse Set</title>" in html


def test_a_query_string_does_not_change_what_is_served(api, cached_set):
    """URL is the state: cols/sort/q/filter/sections are read in the browser."""
    plain = _page(api, f"/sets/{cached_set}")

    withview = _page(api, f"/sets/{cached_set}?cols=3&sort=name&filter=need")

    assert withview == plain


@pytest.mark.parametrize("asset", PAGE_ASSETS)
def test_every_asset_the_page_names_is_served(api, asset):
    status, body = api.get_raw(asset)

    assert status == 200, f"{asset} -> {status}"
    assert body


def test_the_page_names_no_asset_this_test_does_not_know_about(api, cached_set):
    """Keeps PAGE_ASSETS honest when a future change adds a dependency."""
    html = _page(api, f"/sets/{cached_set}")

    named = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', html))

    assert named - {"/static/favicon.ico"} == set(PAGE_ASSETS)
