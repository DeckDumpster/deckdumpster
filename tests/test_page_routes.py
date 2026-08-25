"""The server's page-route table is well-formed and its allowlist is not stale.

These run without a container — the nav-reachability suite that consumes the
table needs a browser, but the table's own invariants do not, and a typo'd
template name should not have to wait for the UI tier to surface.
"""

from pathlib import Path

import pytest

from mtg_collector.cli.page_routes import PAGE_ROUTES, match_page_route
from tests.ui.test_nav_reachability import NAV_EXEMPT

STATIC_DIR = Path(__file__).resolve().parent.parent / "mtg_collector" / "static"


@pytest.mark.parametrize("route", PAGE_ROUTES, ids=lambda r: r.path)
def test_every_route_names_a_file_that_exists(route):
    assert (STATIC_DIR / route.template).is_file(), route.template


@pytest.mark.parametrize("route", PAGE_ROUTES, ids=lambda r: r.path)
def test_a_parametrized_route_is_a_prefix_and_an_exact_one_is_not(route):
    """`/decks/` matches by startswith, so the trailing slash is load-bearing.

    Without it `/decks` would swallow `/decksomething`; with it on an exact
    route, the page would only answer on a URL nobody links.
    """
    assert route.path.endswith("/") == route.parametrized or route.path == "/"


def test_exact_routes_are_unique():
    exact = [r.path for r in PAGE_ROUTES if not r.parametrized]
    assert len(exact) == len(set(exact))


def test_a_longer_prefix_wins_over_a_shorter_one():
    """Prefix order is by length, not declaration order."""
    assert match_page_route("/decks/12").template == "deck_builder.html"
    assert match_page_route("/decks").template == "decks.html"


def test_api_and_static_paths_are_not_pages():
    for path in ("/api/decks", "/api/collection", "/static/shared.js", "/nope"):
        assert match_page_route(path) is None, path


def test_the_nav_allowlist_only_names_real_routes():
    """An exemption for a route that no longer exists is dead weight.

    It also hides a real regression: re-add the path later with no nav link and
    the stale entry silently excuses it.
    """
    routed = {r.path for r in PAGE_ROUTES if not r.parametrized}

    unknown = sorted(set(NAV_EXEMPT) - routed)

    assert not unknown, f"NAV_EXEMPT names paths the server does not route: {unknown}"
