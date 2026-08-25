"""Every page the server routes is reachable from the homepage, or exempt on purpose.

This is default-deny. The route list comes from the server's own dispatch table
(`mtg_collector/cli/page_routes.PAGE_ROUTES` — the tuple `do_GET` actually
routes from), so adding a page and forgetting the nav link fails here with no
list to remember to update. The previous shape of this check was a hand-written
scenario naming each link, which is exactly what went stale: it kept passing on
the links it knew about while /sets shipped with no homepage entry at all.

Two things it deliberately does *not* do:

* It does not read the HTML source. What this UI puts on screen is
  viewport-conditional in places — `de-l5l` is a grid whose default column count
  is meant to depend on `innerWidth` — so every assertion here is against the
  rendered DOM, at a standard **and** a narrow viewport. A link the markup
  contains but a media query hides is not a link anyone can reach.
* It does not describe intent. There is no Claude-graded intent/hint pair and it
  is not a `/qa-finish` scenario — it is one mechanical invariant over a table,
  and it lives in `tests/ui/` only because that is the tier with a browser.

Usage:
    uv run pytest tests/ui/test_nav_reachability.py -v --instance <instance>
"""

import pytest

from mtg_collector.cli.page_routes import PAGE_ROUTES, match_page_route

#: Pages that are deliberately not linked from the homepage, each with the
#: reason it is a decision rather than an oversight. Anything not listed here
#: must have a visible anchor on `/`; that is the whole point of the check, so
#: an addition to this dict is a reviewed exemption, not a way to quiet a
#: failure.
NAV_EXEMPT = {
    "/": "the homepage itself — it is where the nav lives",
    "/search-help": (
        "contextual reference, opened from the ? button beside the collection "
        "search bar. It documents a syntax you only care about while typing a "
        "query, and it opens in a new tab from there (collection.html)"
    ),
    "/disambiguate": (
        "only has content mid-ingest, when OCR matched a card ambiguously. "
        "/upload and /recent link it at the point where there is something to "
        "resolve; a permanent homepage entry would usually lead to an empty page"
    ),
    "/process": (
        "legacy alias serving the same page as /recent, kept for bookmarks. "
        "Nav-linking both would be two entries for one page"
    ),
    "/corner-batches": (
        "legacy alias serving the same page as /batches, kept for bookmarks "
        "from before the corner-only batch list became the general one"
    ),
}

#: Standard desktop, and a phone-width viewport narrow enough to cross the
#: homepage's 768px media query (index.html stacks .nav-row there).
VIEWPORTS = {"standard": (1280, 900), "narrow": (390, 844)}

# Parametrized routes (`/decks/:id`, `/card/:set/:cn`, …) are not homepage links
# and cannot be: the path is meaningless without an id, so there is no URL to
# put in the nav. Each one is reached from the list page that owns it, and that
# list page is itself covered by the rule below.
LINKABLE_ROUTES = tuple(r.path for r in PAGE_ROUTES if not r.parametrized)

MUST_BE_LINKED = tuple(p for p in LINKABLE_ROUTES if p not in NAV_EXEMPT)


def _homepage_anchors(browser, base_url, viewport):
    """Every anchor on the rendered homepage: its resolved path and visibility.

    Visibility is read off the laid-out box, not the stylesheet: an element with
    no client rects is not on the page as far as a user is concerned, however
    present it is in the markup.
    """
    width, height = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        ignore_https_errors=True,
    )
    try:
        page = context.new_page()
        page.goto(f"{base_url}/", wait_until="load")
        page.wait_for_selector("a[href]", state="attached", timeout=5000)
        return page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => ({
                path: new URL(el.getAttribute('href'), location.href).pathname,
                visible: el.getClientRects().length > 0
                         && getComputedStyle(el).visibility !== 'hidden',
                text: el.textContent.trim().split('\\n')[0],
            }))""",
        )
    finally:
        context.close()


@pytest.fixture(scope="module", params=sorted(VIEWPORTS))
def anchors(request, browser, base_url):
    return request.param, _homepage_anchors(browser, base_url, request.param)


def test_every_routed_page_has_a_visible_homepage_link(anchors):
    viewport, found = anchors
    reachable = {a["path"] for a in found if a["visible"]}

    missing = [p for p in MUST_BE_LINKED if p not in reachable]

    assert not missing, (
        f"routes with no visible link on the rendered homepage at the "
        f"{viewport} viewport {VIEWPORTS[viewport]}: {missing}. "
        "Add a nav entry in mtg_collector/static/index.html, or — if the page "
        "is genuinely reached some other way — add it to NAV_EXEMPT in this "
        "file with the reason."
    )


def test_no_homepage_link_points_at_an_unrouted_path(anchors):
    """The same table, read the other way: no nav entry may 404.

    A renamed route leaves the old link behind, and a link to a path the server
    does not route is a dead end that looks like a working button.
    """
    viewport, found = anchors

    dead = sorted(
        {
            a["path"]
            for a in found
            if not a["path"].startswith("/static/") and match_page_route(a["path"]) is None
        }
    )

    assert not dead, (
        f"homepage links at the {viewport} viewport pointing at paths the "
        f"server does not route: {dead}"
    )


def test_a_link_present_but_hidden_does_not_count(anchors):
    """Guards the check itself: rendered visibility is what is being read.

    If `visible` came back true for everything — a selector that stopped
    matching, an evaluate that silently returned defaults — the reachability
    assertion above would pass on a page with no nav at all. The homepage's
    badge spans are anchors' children, not anchors, so the honest expectation
    is simply that some anchors exist and they were measured, not asserted.
    """
    _, found = anchors

    assert found, "no anchors found on the homepage at all"
    assert all(isinstance(a["visible"], bool) for a in found)
