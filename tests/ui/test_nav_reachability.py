"""Navigation works in both directions: every page is reachable from `/`, and gets back.

Two invariants over one table. Forward: every routed page has a visible link on
the homepage. Back: every routed page renders a visible link to `/`. They are
complements, and they belong together — /sets/:set_code shipped reachable from
the homepage and with no way off it at all, which the forward check alone is
blind to by construction.

This is default-deny in both directions. The route list comes from the server's
own dispatch table (`mtg_collector/cli/page_routes.PAGE_ROUTES` — the tuple
`do_GET` actually routes from), so adding a page and forgetting the nav link
fails here with no list to remember to update. The previous shape of this check
was a hand-written scenario naming each link, which is exactly what went stale:
it kept passing on the links it knew about while /sets shipped with no homepage
entry at all.

Two things it deliberately does *not* do:

* It does not read the HTML source. What this UI puts on screen is
  viewport-conditional in places — `de-l5l` is a grid whose default column count
  is meant to depend on `innerWidth` — so every assertion here is against the
  rendered DOM, at a standard **and** a narrow viewport. A link the markup
  contains but a media query hides is not a link anyone can reach.
* It does not describe intent. There is no Claude-graded intent/hint pair and it
  is not a `/qa-finish` scenario — these are mechanical invariants over a table,
  and they live in `tests/ui/` only because that is the tier with a browser.

Usage:
    uv run pytest tests/ui/test_nav_reachability.py -v --instance <instance>
"""

import pytest

from mtg_collector.cli.page_routes import PAGE_ROUTES, match_page_route

from .budget import ROUND_TRIP_BUDGET_MS, budget_ms

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
        "serves the same page as /recent (the ingest status list), kept for "
        "bookmarks from when processing had its own URL. Nothing links it and "
        "nothing should: two nav entries for one page is not navigation"
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

#: Pages that deliberately render no link back to `/`. The homepage is the only
#: one: it *is* `/`. Unlike NAV_EXEMPT there is no such thing as a page a user
#: navigates to and should then be stuck on — an alias, a deep link and a
#: mid-ingest resolution screen all still need a way out — so an entry here
#: wants a better reason than "nothing links it".
HOME_LINK_EXEMPT = {
    "/": "the homepage itself — a link from `/` to `/` is not navigation",
}

#: One concrete URL per parametrized route, because a prefix is not a page you
#: can open. The id need not resolve: every one of these pages ships its chrome
#: as static markup and fills the body from an API call afterwards, so a
#: placeholder exercises the same header a real id would — and keeps this suite
#: independent of whatever happens to be in the instance's database.
#:
#: Parametrized routes are emphatically *not* exempt from the back-link rule.
#: /sets/:set_code is one, and it is the page that motivated this check.
PARAMETRIZED_SAMPLES = {
    "/deck-builder/": "/deck-builder/1",
    "/decks/": "/decks/1",
    "/sets/": "/sets/fdn",
    "/card/": "/card/fdn/1",
    "/batches/": "/batches/1",
    "/orders/": "/orders/1",
}


def _pages_that_must_link_home():
    """Every routed page as a URL you can actually open, minus the exemptions.

    Reading the parametrized samples out of the same table is what keeps this
    default-deny: a new `PageRoute(..., parametrized=True)` with no sample here
    fails `test_every_parametrized_route_has_a_sample_url` rather than quietly
    dropping out of the sweep.
    """
    paths = []
    for route in PAGE_ROUTES:
        if route.path in HOME_LINK_EXEMPT:
            continue
        sample = PARAMETRIZED_SAMPLES.get(route.path) if route.parametrized else route.path
        if sample is not None:
            paths.append(sample)
    return tuple(paths)


MUST_LINK_HOME = _pages_that_must_link_home()

#: Reads an anchor to `/` off the rendered page, on the same terms the homepage
#: sweep reads its own: laid-out box, not stylesheet.
_HAS_VISIBLE_HOME_LINK = """els => els.some(el =>
    new URL(el.getAttribute('href'), location.href).pathname === '/'
    && el.getClientRects().length > 0
    && getComputedStyle(el).visibility !== 'hidden')"""


def _homepage_anchors(browser, base_url, viewport, extra_css=None):
    """Every anchor on the rendered homepage: its resolved path and visibility.

    Visibility is read off the laid-out box, not the stylesheet: an element with
    no client rects is not on the page as far as a user is concerned, however
    present it is in the markup.

    `extra_css` is only for the self-check below, which hides a known link to
    prove that hiding one is noticed.
    """
    width, height = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        ignore_https_errors=True,
    )
    try:
        page = context.new_page()
        page.goto(
            f"{base_url}/",
            wait_until="load",
            timeout=budget_ms(ROUND_TRIP_BUDGET_MS),
        )
        page.wait_for_selector(
            "a[href]", state="attached", timeout=budget_ms(ROUND_TRIP_BUDGET_MS)
        )
        if extra_css:
            page.add_style_tag(content=extra_css)
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


def test_a_link_the_markup_has_and_a_media_query_hides_does_not_count(browser, base_url):
    """The self-check: proves the narrow viewport is doing real work.

    Everything above rests on `visible` meaning something. If the probe reported
    True for every anchor — a selector that stopped matching, an evaluate that
    quietly returned defaults — the reachability assertion would pass on a page
    with no usable nav at all, which is the failure it exists to catch. So hide
    one real link at narrow widths only and require the reading to change: it is
    reachable at 1280px and unreachable at 390px, from identical markup. Source
    inspection cannot tell those two apart.
    """
    hide_at_narrow = "@media (max-width: 768px) { a[href='/sets'] { display: none } }"

    wide = {a["path"] for a in _homepage_anchors(browser, base_url, "standard", hide_at_narrow) if a["visible"]}
    narrow = {a["path"] for a in _homepage_anchors(browser, base_url, "narrow", hide_at_narrow) if a["visible"]}

    assert "/sets" in wide
    assert "/sets" not in narrow


def _home_links(browser, base_url, viewport):
    """Whether each routed page renders a visible link to `/`, keyed by path.

    One context and one page for the whole sweep: these are ~25 navigations per
    viewport and a fresh context each time is the bulk of the cost. Nothing here
    writes, so there is no state to isolate between them.
    """
    width, height = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        ignore_https_errors=True,
    )
    try:
        page = context.new_page()
        found = {}
        for path in MUST_LINK_HOME:
            page.goto(
                f"{base_url}{path}",
                wait_until="load",
                timeout=budget_ms(ROUND_TRIP_BUDGET_MS),
            )
            page.wait_for_selector(
                "body", state="attached", timeout=budget_ms(ROUND_TRIP_BUDGET_MS)
            )
            found[path] = page.eval_on_selector_all("a[href]", _HAS_VISIBLE_HOME_LINK)
        return found
    finally:
        context.close()


@pytest.fixture(scope="module", params=sorted(VIEWPORTS))
def home_links(request, browser, base_url):
    return request.param, _home_links(browser, base_url, request.param)


def test_every_routed_page_links_back_to_the_homepage(home_links):
    """The complement of the forward check: a page you can reach and not leave.

    /sets/:set_code was exactly that — linked from /sets, carrying one anchor of
    its own (`#batch-link`, hidden unless a batch is open), so the only ways off
    it were the back button and the URL bar.
    """
    viewport, found = home_links

    stranded = sorted(path for path, has_link in found.items() if not has_link)

    assert not stranded, (
        f"pages rendering no visible link to / at the {viewport} viewport "
        f"{VIEWPORTS[viewport]}: {stranded}. Give the page the shared site "
        "header (`.site-header`, as /sets and /card/:set/:cn have it), or — if "
        "it is genuinely a page nobody should leave forwards — add it to "
        "HOME_LINK_EXEMPT in this file with the reason."
    )


def test_every_parametrized_route_has_a_sample_url():
    """The sweep above can only be default-deny if it opens every route.

    A parametrized route is a prefix, not a URL, so it needs a sample to be
    visited at all — and a missing sample would drop the page out of the sweep
    silently, which is how a check comes to pass on a page it never loaded.
    """
    parametrized = {r.path for r in PAGE_ROUTES if r.parametrized}
    unsampled = sorted(parametrized - set(PARAMETRIZED_SAMPLES))

    assert not unsampled, (
        f"parametrized routes with no sample URL: {unsampled}. Add one to "
        "PARAMETRIZED_SAMPLES in this file so the back-link sweep opens the "
        "page; the id does not have to resolve."
    )

    stale = sorted(set(PARAMETRIZED_SAMPLES) - parametrized)
    assert not stale, (
        f"PARAMETRIZED_SAMPLES entries for routes the server no longer has: "
        f"{stale}"
    )


def test_a_sample_url_actually_reaches_its_page(browser, base_url):
    """The self-check for the sweep: a placeholder id still serves the page.

    The back-link assertion reads anchors off whatever came back. If a sample
    URL 404'd — or served an error page that happens to link home — every route
    behind it would report "fine" from a page that is not the one under test. So
    require one sample to arrive at its own template, identified by an element
    only that page has.
    """
    context = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    try:
        page = context.new_page()
        response = page.goto(
            f"{base_url}{PARAMETRIZED_SAMPLES['/sets/']}",
            wait_until="load",
            timeout=budget_ms(ROUND_TRIP_BUDGET_MS),
        )
        assert response.status == 200, response.status
        # #set-name and the section pills belong to set_browse.html alone.
        assert page.query_selector("#set-name") is not None
        assert page.query_selector("#sections [data-section='base']") is not None
    finally:
        context.close()
