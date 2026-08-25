"""The /sets index page: its route, and the rules its markup has to keep.

Tier 1 — no container, no network. `do_GET` reads only `self.path`, so the
dispatch table can be driven against a handler built without a socket, the way
`test_search_alias.py` does.

Most of the page's behaviour is JavaScript and belongs to the UI scenario
tests. What is worth pinning here is what is invisible from either side alone:
the route exists and points at a file that exists, that file loads the two
scripts whose globals `sets.js` calls without declaring, and the group order is
what `SET_TYPE_RANK` says rather than what the payload happened to arrive in.

That last one is here and not in `tests/ui/` on purpose. A scenario test runs
against the fixture database, and the fixture's newest set is an expansion — so
it reads Expansion-first whether the rank exists or not. The invariant only
shows up against a payload no fixture will produce, so these drive the real
page (real `sets.html`, real scripts, `/api/sets/index` answered synthetically)
in a browser and read the order back out of the DOM.
"""

import inspect
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"

# Nothing listens on it — every request is fulfilled from disk below. It exists
# so the page has an origin to resolve `/api/sets/index` against, which
# `about:blank` does not.
PAGE_URL = "https://sets.test/sets"

_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


def _bare_handler(path: str):
    handler = object.__new__(cps.CrackPackHandler)
    handler.path = path
    return handler


def test_sets_route_serves_the_page():
    handler = _bare_handler("/sets")

    with patch.object(cps.CrackPackHandler, "_serve_static") as serve:
        handler.do_GET()

    serve.assert_called_once_with("sets.html")


def test_sets_route_does_not_swallow_the_set_code_page():
    """`/sets/:set_code` is a separate page (de-k5o's item 7), so the index's
    branch must be an exact match — `startswith` here would serve the index for
    every set and the binder grid would never be reachable."""
    source = inspect.getsource(cps.CrackPackHandler.do_GET)
    assert 'elif path == "/sets":' in source
    assert 'path.startswith("/sets")' not in source


def test_page_assets_exist():
    for name in ("sets.html", "sets.css", "sets.js"):
        assert (STATIC / name).is_file(), f"{name} missing"


def test_page_loads_the_globals_sets_js_calls():
    """`sets.js` calls `esc` (shared.js) and `keyruneSetCode`
    (shared-card-table.js, which is where KEYRUNE_FALLBACKS lives) as bare
    globals. Nothing in the browser complains until the page runs, so the
    script tags are asserted here."""
    html = (STATIC / "sets.html").read_text()
    for src in ("/static/shared.js", "/static/shared-card-table.js", "/static/sets.js"):
        assert f'src="{src}"' in html, f"{src} not loaded by sets.html"
    assert 'href="/static/vendor/keyrune/keyrune.min.css"' in html, (
        "set symbols are keyrune glyphs; without the font every tile shows a blank"
    )


def test_no_nan_meter_can_be_rendered():
    """A set with no `base_set_size` reports `total_base` as null, and the meter
    is hidden rather than drawn as 0 / 0. The guard is `total > 0`, which is
    false for null — a bare `total != null` or a `||` default would render the
    NaN this page exists not to show."""
    js = (STATIC / "sets.js").read_text()
    assert "if (!(total > 0)) return '';" in js


def _set(code, set_type, released_at, name=None):
    """One row of `/api/sets/index`. The meters are what the endpoint sends for
    a set nothing is owned from; only the type and the date matter here."""
    return {
        "set_code": code,
        "set_name": name or code.upper(),
        "set_type": set_type,
        "released_at": released_at,
        "owned_base": 0,
        "total_base": 100,
        "owned_all": 0,
        "total_all": 120,
    }


def _fulfill(route, payload):
    path = urlparse(route.request.url).path
    if path == "/api/sets/index":
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        return
    file = STATIC / "sets.html" if path == "/sets" else STATIC / path.removeprefix("/static/")
    if path.startswith("/static/") or path == "/sets":
        if file.is_file():
            route.fulfill(
                status=200,
                content_type=_CONTENT_TYPES.get(file.suffix, "application/octet-stream"),
                body=file.read_bytes(),
            )
            return
    # Keyrune ships font files the stylesheet asks for; a glyph nobody looks at
    # is not worth serving.
    route.fulfill(status=404, body="")


@pytest.fixture(scope="module")
def browser():
    """Chromium from the Playwright the UI tests already depend on — no
    container and no network, so this stays a tier-1 test. Install once with
    `uv run shot-scraper install`."""
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def load_sets(browser):
    """Drive the real /sets page against a synthetic index payload. Returns the
    rendered group order (document order) and anything the page threw."""

    pages = []

    def load(payload):
        page = browser.new_page()
        pages.append(page)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda route: _fulfill(route, payload))
        page.goto(PAGE_URL)
        page.wait_for_selector("#sets-body section.set-group")
        order = page.eval_on_selector_all(
            "#sets-body > section.set-group", "els => els.map(e => e.dataset.setType)"
        )
        return page, order, errors

    yield load
    for page in pages:
        page.close()


def test_group_order_is_the_rank_not_the_release_order(load_sets):
    """The bug this replaced: the leading group was whichever set_type owned the
    single most recently released cached set, so it moved when Marvel Super
    Heroes Commander tied a release date with an expansion and again when the
    Hobbit sets were imported. Newest here is a token; Expansion still leads."""
    page, order, errors = load_sets(
        [
            _set("tokn", "token", "2026-08-24"),
            _set("pmoc", "promo", "2026-08-20"),
            _set("cmdr", "commander", "2026-08-15"),
            _set("expn", "expansion", "2026-01-23"),
        ]
    )

    assert order == ["expansion", "commander", "token", "promo"]
    assert errors == []
    # Every set still has its tile — the rank orders groups, it does not filter.
    assert page.locator("a.set-tile").count() == 4


def test_an_unknown_set_type_falls_to_the_end(load_sets):
    """Scryfall adds set types, and one the rank has never heard of must render
    at the end rather than dropping out or throwing — otherwise the list needs
    maintenance to stay correct, not just to stay optimal."""
    page, order, errors = load_sets(
        [
            _set("newt", "some_future_type", "2026-08-24"),
            _set("tokn", "token", "2026-08-20"),
            _set("expn", "expansion", "2026-01-23"),
        ]
    )

    assert order == ["expansion", "token", "some_future_type"]
    assert errors == []
    assert page.locator("a.set-tile").count() == 3
    # setTypeLabel titlecases whatever arrives, so the group is legible without
    # anyone having added it to a label map. Read the DOM text, not the rendered
    # text — sets.css uppercases the heading, which would hide a missing label.
    heading = page.locator("section[data-set-type='some_future_type'] h2").text_content()
    assert heading.startswith("Some Future Type")


def test_unranked_types_keep_the_response_order_among_themselves(load_sets):
    """They all share one rank, so the sort must be stable — newest-first is
    what the response carries and there is nothing better to fall back on."""
    _, order, errors = load_sets(
        [
            _set("newa", "future_a", "2026-08-24"),
            _set("newb", "future_b", "2026-08-20"),
            _set("expn", "expansion", "2026-01-23"),
        ]
    )

    assert order == ["expansion", "future_a", "future_b"]
    assert errors == []


def test_rank_covers_the_set_types_the_page_actually_sees():
    """A type missing from the rank still renders, but at the end — which for a
    common one is wrong, not merely unsorted. These are the types the endpoint
    can return today."""
    js = (STATIC / "sets.js").read_text()
    for set_type in ("expansion", "core", "commander", "masters", "draft_innovation", "token", "promo"):
        assert f"'{set_type}'" in js, f"{set_type} missing from SET_TYPE_RANK"
