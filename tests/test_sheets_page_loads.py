"""The /sheets page's loading rules: one fetch per selection, newest wins.

Tier 1 — no container, no network. The real `explore_sheets.html` runs in a
browser against synthetic `/api/sets`, `/api/products` and `/api/sheets`
payloads, the way `test_sets_page.py` drives the real `/sets` page.

What is pinned here is invisible from either side alone. The bug (de-8ea) was
that `loadProducts()` checked the first product unconditionally and loaded it,
and the deep-link path then re-checked the one the hash asked for — so
`/sheets#set=blb&product=play` fetched `collector` (240 KB, rendered, then
thrown away) before `play`. The server sees two well-formed requests and the
page ends up correct, so neither an API test nor a scenario assertion on the
final DOM can see it. Counting the requests the page issues can.

The same is true of the two rules that follow from it: a superseded load must
not land in the DOM behind the newer one, and a load in flight must not blank
the sheets already on screen. Both are about what the page does *between* two
states, which is why the responses here are delayed from inside the page
rather than served at whatever speed a container happens to manage.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import sync_playwright

from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.cli.page_routes import match_page_route

STATIC = Path(cps.__file__).resolve().parent.parent / "static"

# Nothing listens on it — every request is fulfilled from disk or from the
# payloads below. It exists so the page has an origin to resolve `/api/*`
# against, which `about:blank` does not.
PAGE_URL = "https://sheets.test/sheets"

_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}

SETS = [{"code": "blb", "name": "Bloomburrow"}]

# The order matters: `collector` is first, so it is what the old code loaded
# before the hash got a say. Two products with different sheet names is the
# smallest payload that can tell which one reached the DOM.
PRODUCTS = ["collector", "play"]

# Sheet name and card count both differ per product, so the content area and
# the status line each say on their own which product reached the DOM.
SHEETS = {"collector": ("collectorRare", 7), "play": ("playCommon", 9)}


def _sheets_payload(product):
    """One sheet, no cards. `buildCardTile` is the card grid's business and has
    its own coverage; an empty sheet still renders the section header and the
    status line, which is all these tests read."""
    name, card_count = SHEETS[product]
    return {
        "set_code": "blb",
        "product": product,
        "total_weight": 100,
        "variants": [{"index": 0, "weight": 100, "probability": 1.0, "contents": {name: 1}}],
        "sheets": {name: {"foil": False, "total_weight": 100, "card_count": card_count, "cards": []}},
    }


def _fulfill(route, sheets_requests):
    url = urlparse(route.request.url)
    path = url.path
    if path == "/api/sets":
        route.fulfill(status=200, content_type="application/json", body=json.dumps(SETS))
        return
    if path == "/api/settings":
        route.fulfill(status=200, content_type="application/json", body=json.dumps({}))
        return
    if path == "/api/products":
        route.fulfill(status=200, content_type="application/json", body=json.dumps(PRODUCTS))
        return
    if path == "/api/sheets":
        product = parse_qs(url.query)["product"][0]
        sheets_requests.append(product)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_sheets_payload(product)),
        )
        return
    file = STATIC / "explore_sheets.html" if path == "/sheets" else STATIC / path.removeprefix("/static/")
    if (path.startswith("/static/") or path == "/sheets") and file.is_file():
        route.fulfill(
            status=200,
            content_type=_CONTENT_TYPES.get(file.suffix, "application/octet-stream"),
            body=file.read_bytes(),
        )
        return
    route.fulfill(status=404, body="")


def _wait_for_sheets(page):
    """`#status` is written last, after the section-render loop finishes, so it
    is the only signal that a load has fully landed."""
    page.wait_for_function("document.getElementById('status').textContent.includes('sheets,')")


@pytest.fixture(scope="module")
def browser():
    """Chromium from the Playwright the UI tests already depend on — no
    container and no network, so this stays a tier-1 test. Install once with
    `uv run playwright install chromium`."""
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def load_sheets(browser):
    """Drive the real /sheets page and hand back the page, the products it
    asked `/api/sheets` for in order, and anything it threw."""

    pages = []

    def load(hash_part=""):
        page = browser.new_page()
        pages.append(page)
        errors = []
        sheets_requests = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda route: _fulfill(route, sheets_requests))
        page.goto(PAGE_URL + hash_part)
        # No hash means no selection, so there are no sheets to wait for —
        # the set input becoming enabled is where that page is ready.
        if hash_part:
            page.wait_for_selector(".section-header")
            _wait_for_sheets(page)
        else:
            page.wait_for_selector("#set-input:not([disabled])")
        return page, sheets_requests, errors

    yield load
    for page in pages:
        page.close()


def test_deep_link_fetches_only_the_product_it_names(load_sheets):
    """de-8ea. The old path checked the first product, loaded it, and only then
    let the hash select another — so every deep link to a non-first product
    fetched, parsed and rendered a payload it immediately discarded, and the
    two responses raced for the DOM on the way."""
    page, requests, errors = load_sheets("#set=blb&product=play")

    assert requests == ["play"], f"expected one fetch for `play`, got {requests}"
    assert page.eval_on_selector('input[name="product"]:checked', "e => e.value") == "play"
    assert "Play Common" in page.inner_text("#content")
    assert errors == []


def test_deep_link_to_an_absent_product_falls_back_to_the_first(load_sheets):
    """A hash naming a product this set does not have still loads the set, once.
    That is what the old re-check did too — it simply found no radio to check —
    so the fallback is preserved behaviour, not new modality."""
    page, requests, errors = load_sheets("#set=blb&product=nonesuch")

    assert requests == ["collector"], f"expected one fetch for `collector`, got {requests}"
    assert page.eval_on_selector('input[name="product"]:checked', "e => e.value") == "collector"
    assert errors == []


def test_selecting_a_set_by_hand_fetches_one_product(load_sheets):
    """The interactive path shares `loadProducts`, so it is pinned here too:
    picking a set loads the first product's sheets and nothing else."""
    page, requests, errors = load_sheets()

    page.fill("#set-input", "Bloom")
    page.click("#set-dropdown li")
    _wait_for_sheets(page)

    assert requests == ["collector"], f"expected one fetch, got {requests}"
    assert errors == []


# Applied inside the page so the delay is the test's, not the transport's: it
# holds `/api/sheets` for the named product long enough that the assertions
# below are about ordering rather than about how fast a route handler ran.
_DELAY_PRODUCT = """
([product, ms]) => {
  const orig = window.fetch;
  window.fetch = (url, opts) => {
    if (String(url).includes('product=' + product)) {
      return new Promise(resolve => setTimeout(() => resolve(orig(url, opts)), ms));
    }
    return orig(url, opts);
  };
}
"""


def test_a_load_in_flight_does_not_blank_the_sheets_on_screen(load_sheets):
    """`loadSheets` used to open by writing "Loading sheets..." over `content`,
    so switching product flashed an empty page over sheets that were still
    perfectly valid. The replacement is built off-document and swapped in whole."""
    page, requests, errors = load_sheets("#set=blb&product=play")

    before = page.inner_text("#content")
    assert "Play Common" in before

    page.evaluate(_DELAY_PRODUCT, ["collector", 500])
    page.click('label[for="product-collector"]')

    assert page.inner_text("#content") == before, "content was blanked before the replacement arrived"

    page.wait_for_function("document.getElementById('status').textContent === '1 sheets, 7 cards'")
    assert "Collector Rare" in page.inner_text("#content")
    assert "Play Common" not in page.inner_text("#content")
    assert errors == []


def test_the_newest_load_wins_even_when_it_answers_first(load_sheets):
    """Two loads really can be in flight — switch product while the first is
    still downloading. Nothing sequences them, so without a supersede the
    slower response renders last and the page shows a product nobody asked
    for. Here the *older* load is the slow one, which is the order that used to
    lose.

    This one held before the fix too — de-ear left a request token behind that
    kept the stale response out of the DOM. The token is gone now, replaced by
    an abort that also stops the transfer, so the rule it guarded is pinned
    here rather than left resting on a comment."""
    page, requests, errors = load_sheets("#set=blb&product=play")

    page.evaluate(_DELAY_PRODUCT, ["collector", 500])
    page.click('label[for="product-collector"]')
    page.click('label[for="product-play"]')

    # Long enough that the superseded `collector` response has come and gone.
    page.wait_for_timeout(1200)

    assert "Play Common" in page.inner_text("#content")
    assert "Collector Rare" not in page.inner_text("#content")
    assert page.inner_text("#status") == "1 sheets, 9 cards"
    assert errors == []


def test_sheets_route_serves_the_page():
    """The tests above drive `explore_sheets.html` directly, so the route that
    reaches it in the real server is asserted separately."""
    route = match_page_route("/sheets")
    assert route is not None
    assert route.template == "explore_sheets.html"
    assert not route.parametrized
