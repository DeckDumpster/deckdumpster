"""Set-browse tiles show the collector number left of the finish pips.

Tier 1 -- the real `set_browse.html` in Chromium against a synthetic
`/api/set-browse/fra`, as `test_set_browse_grid_cols.py` does. The number is the
stored string behind a `#`, never parsed; it shares one non-wrapping row with the
pips, as the pokedumpster / dumpstar `CardTile` footer does (sp-28d4u3).

To run: uv run pytest tests/test_set_browse_tile_number.py -v
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"
PAGE_URL = "https://setbrowse.test/sets/fra"
_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


def _row(pid, number, finishes):
    return {
        "printing_id": pid,
        "set_code": "fra",
        "collector_number": number,
        "name": f"Card {number}",
        "rarity": "rare",
        "image_uri": "",
        "finishes": json.dumps(finishes),
        "owned": [{"finish": f, "qty": 0} for f in finishes],
        "qty": 0,
        "section": "base",
    }


_BOTH = ["nonfoil", "foil"]
ROWS = [
    _row("p345", "345", _BOTH),
    _row("p12a", "12a", _BOTH),
    _row("pstar", "★7", _BOTH),
    _row("pnone", "99", []),
    # No number at all: its row is just the pips, the height every other row
    # has to equal.
    _row("pbare", "", _BOTH),
]
_PAYLOAD = {
    "rows": ROWS,
    "total": len(ROWS),
    "set": {"set_name": "Final Fantasy: Fra"},
    "owned_base": None,
    "total_base": None,
    "owned_all": None,
    "total_all": None,
}


ADDS = []


def _fulfill(route):
    path = urlparse(route.request.url).path
    if path == "/api/collection" and route.request.method == "POST":
        ADDS.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"batch_id": 1}')
        return
    if path == "/api/settings":
        route.fulfill(status=200, content_type="application/json", body="{}")
        return
    if path.startswith("/api/set-browse/"):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(_PAYLOAD))
        return
    file = STATIC / "set_browse.html" if path.startswith("/sets/") else None
    if file is None and path.startswith("/static/"):
        file = STATIC / path.removeprefix("/static/")
    if file is not None and file.is_file():
        route.fulfill(
            status=200,
            content_type=_CONTENT_TYPES.get(file.suffix, "application/octet-stream"),
            body=file.read_bytes(),
        )
        return
    route.fulfill(status=404, body="")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def load(browser):
    contexts = []

    def go(width, query=""):
        ctx = browser.new_context(viewport={"width": width, "height": 844})
        contexts.append(ctx)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda route: _fulfill(route))
        page.goto(PAGE_URL + query)
        page.wait_for_selector(".sheet-card")
        assert not errors, f"page threw: {errors}"
        return page

    yield go
    for ctx in contexts:
        ctx.close()


@pytest.mark.parametrize(
    "pid,expected",
    [("p345", "#345"), ("p12a", "#12a"), ("pstar", "#★7")],
)
def test_the_number_leads_the_row_that_holds_the_pips(load, pid, expected):
    page = load(1280)
    tile = page.locator(f'.sheet-card[data-printing-id="{pid}"]')

    assert tile.locator(".pip-row .tile-num").inner_text() == expected
    first_is_num = tile.locator(".pip-row").evaluate(
        "row => row.firstElementChild.classList.contains('tile-num')"
        " && row.querySelectorAll('.pips .finish-pip').length === 2"
    )
    assert first_is_num


def test_a_printing_with_no_finishes_still_shows_its_number(load):
    page = load(1280)
    tile = page.locator('.sheet-card[data-printing-id="pnone"]')

    assert tile.locator(".pip-row .tile-num").inner_text() == "#99"
    assert tile.locator(".finish-pip").count() == 0


@pytest.mark.parametrize("width", [1280, 390])
def test_the_row_never_wraps_or_widens_the_page(load, width):
    page = load(width, "?cols=9")
    baseline = page.evaluate(
        "document.querySelector('.sheet-card[data-printing-id=\"pbare\"] .pip-row').offsetHeight"
    )
    heights = page.evaluate(
        "[...document.querySelectorAll('.pip-row')].map(r => r.offsetHeight)"
    )
    assert baseline == 18
    assert heights and all(h == baseline for h in heights), heights
    # Nothing is clipped sideways: the pips shrank, the number ellipsised.
    assert page.evaluate(
        "[...document.querySelectorAll('.pip-row')].every(r => r.scrollWidth <= r.clientWidth)"
    )
    assert page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth"
    )


def test_clicking_a_pip_through_its_wrapper_still_adds_that_finish(load):
    ADDS.clear()
    page = load(1280)
    page.locator(
        '.sheet-card[data-printing-id="p345"] .finish-pip[data-finish="foil"]'
    ).click()
    page.wait_for_timeout(200)

    assert [(a["printing_id"], a["finish"]) for a in ADDS] == [("p345", "foil")]


def test_tiles_that_ask_for_neither_option_render_no_footer(load):
    """explore_sheets.html passes neither showPips nor showNumber."""
    page = load(1280)
    html = page.evaluate(
        "buildCardTile({name:'x', collector_number:'5', set_code:'fra',"
        " finishes:'[\"nonfoil\"]', owned:[]}, {})"
    )
    assert "pip-row" not in html and "tile-num" not in html
