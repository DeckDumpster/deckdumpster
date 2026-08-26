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


#: `shared.<64 bits of hex>.js` -> `shared.js`. The server mints the digest as
#: the page goes out (de-l23), so the name in the markup is not the name on
#: disk and a literal comparison would be a comparison against a deploy.
_DIGEST = re.compile(r"\.[0-9a-f]{16}(\.[^.]+)$")


def _undigest(url: str) -> str:
    return _DIGEST.sub(r"\1", url)


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


def test_a_trailing_slash_serves_the_index_not_an_empty_binder(api):
    """`/sets/` is `/sets`, not the binder for a set whose code is `""`.

    It used to serve this page with an empty code, so the grid asked the API
    for set `''` and rendered "not cached (run `mtg cache all` to populate)" --
    a page that looks like a broken catalogue and is really a stray slash.
    """
    html = _page(api, "/sets/")

    assert "<title>Sets</title>" in html
    assert "<title>Browse Set</title>" not in html


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

    named = {_undigest(u) for u in re.findall(r'(?:src|href)="(/static/[^"]+)"', html)}

    assert named - {"/static/favicon.ico"} == set(PAGE_ASSETS)


def test_the_urls_the_page_actually_names_are_content_addressed(api, cached_set):
    """Since de-l23 the server rewrites each reference to carry the digest of
    the bytes, so what a browser requests is not what the file is called. The
    hashed URL is the one that has to be served -- a page whose scripts 404
    renders an empty grid and reads as an empty set."""
    html = _page(api, f"/sets/{cached_set}")

    named = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert named, "the page names no assets"

    for url in named:
        assert url != _undigest(url), f"{url} carries no digest"
        status, body = api.get_raw(url)
        assert status == 200, f"{url} -> {status}"
        assert body
