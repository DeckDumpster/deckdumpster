"""The binder grid's opening cards-per-row, and the viewport it depends on.

Tier 1 -- no container, no network. The real `set_browse.html` is driven in
Chromium against a synthetic `/api/set-browse/:set_code`, the way
`test_sets_page.py` drives the index.

This is here and not in `tests/ui/` for the reason that file already records:
the behaviour *is* a viewport, and `tests/ui/conftest.py` pins every scenario
context at 1280x900. A container scenario is structurally blind to a default
that only differs below 600px -- it would pass against the bug and against the
fix alike.

The bug (de-l5l): `/sets/:set_code` is the fifth copy of the +/- cards-per-row
control, and it was the only one of the five with no narrow-viewport term. Its
four siblings all pick a smaller opening value on a phone when nothing is
stored (`collection.html` 2, `crack_pack.html` 3, `explore_sheets.html` 3,
`recent.html` 2), and nothing compensated for its absence here: the only
`--grid-cols` consumer is `shared-card-tile.css`, unconditional. A phone opened
the binder at six columns of card art, on the page whose whole job -- counting
a physical binder against what you own -- is the one you do phone-in-hand.

To run: uv run pytest tests/test_set_browse_grid_cols.py -v
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"

# Nothing listens on it -- every request is fulfilled from disk or from the
# stub below. It exists so the page has an origin: `localStorage` is what this
# default yields to, and `about:blank` has none to seed.
PAGE_URL = "https://setbrowse.test/sets/fin"

#: The threshold the four siblings use, and the value /sheets picks -- the page
#: this grid's tile was extracted from -- either side of it.
NARROW, WIDE = 390, 1280
NARROW_COLS, WIDE_COLS = 3, 6

_CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}

#: An empty set is enough. Every assertion here reads a custom property that
#: `syncControls()` sets before the first fetch is even issued; the payload is
#: served only so the page finishes without throwing.
_PAYLOAD = {
    "rows": [],
    "total": 0,
    "set": {"set_name": "Final Fantasy"},
    "owned_base": None,
    "total_base": None,
    "owned_all": None,
    "total_all": None,
}


def _fulfill(route):
    path = urlparse(route.request.url).path
    if path == "/api/settings":
        route.fulfill(status=200, content_type="application/json", body="{}")
        return
    if path.startswith("/api/set-browse/"):
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(_PAYLOAD)
        )
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
    # Keyrune ships font files its stylesheet asks for; a glyph nobody looks at
    # is not worth serving.
    route.fulfill(status=404, body="")


@pytest.fixture(scope="module")
def browser():
    """Chromium from the Playwright the UI tests already depend on -- no
    container and no network, so this stays a tier-1 test. Install once with
    `uv run shot-scraper install`."""
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def open_grid(browser):
    """Load the real binder grid at a given width and read the opening column
    count back out.

    A fresh context per load, not a fresh page: `applyGridCols()` writes
    `setsGridCols` on every load, so a shared context would let the first test
    seed the second and the no-stored-value branch -- the whole subject here --
    would never be taken twice.
    """

    contexts = []

    def load(width, *, stored=None, query=""):
        ctx = browser.new_context(viewport={"width": width, "height": 844})
        contexts.append(ctx)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda route: _fulfill(route))
        if stored is not None:
            # Seeded through a load of the page itself: `localStorage` is
            # per-origin, and this origin only exists once something has been
            # served from it.
            page.goto(PAGE_URL)
            page.evaluate(f"localStorage.setItem('setsGridCols', '{stored}')")
        page.goto(PAGE_URL + query)
        page.wait_for_selector("#col-count")
        cols = page.evaluate(
            "getComputedStyle(document.documentElement)"
            ".getPropertyValue('--grid-cols').trim()"
        )
        assert not errors, f"page threw: {errors}"
        return page, cols

    yield load

    for ctx in contexts:
        ctx.close()


class TestTheOpeningColumnCount:
    def test_a_phone_opens_narrower_than_a_desktop(self, open_grid):
        """The bug, stated as the two readings that have to differ. Against
        `storedCols()` as it was -- a flat `DEFAULTS.cols` with no `innerWidth`
        term -- both sides read 6 and this fails."""
        _, narrow = open_grid(NARROW)
        _, wide = open_grid(WIDE)

        assert narrow == str(NARROW_COLS)
        assert wide == str(WIDE_COLS)

    @pytest.mark.parametrize(
        "width,expected", [(599, NARROW_COLS), (600, WIDE_COLS)]
    )
    def test_the_threshold_is_the_siblings_threshold(self, open_grid, width, expected):
        """600px exactly, and exclusive, because `< 600` is what the other four
        write. A control copied five times is worth having one answer."""
        _, cols = open_grid(width)

        assert cols == str(expected)

    def test_the_count_the_stepper_shows_is_the_count_it_drew(self, open_grid):
        """`--grid-cols` and the `#col-count` readout come from one `view.cols`,
        so a phone that opens at 3 says 3 -- the minus button is not one press
        behind what is on screen."""
        page, cols = open_grid(NARROW)

        assert page.inner_text("#col-count") == cols


class TestWhatStillOutranksIt:
    """A default is the last resort, and stays the last resort. Both of these
    pass before the fix too -- they are here so it cannot be the fix that
    breaks them."""

    def test_a_stored_value_wins_on_a_phone(self, open_grid):
        _, cols = open_grid(NARROW, stored=8)

        assert cols == "8"

    def test_the_url_wins_over_both(self, open_grid):
        _, cols = open_grid(NARROW, stored=8, query="?cols=10")

        assert cols == "10"

    def test_a_stored_value_out_of_range_falls_to_the_default(self, open_grid):
        """The range check `set_browse.html` added over its siblings' bare
        `parseInt(...) || default` is an improvement, and survives: a rejected
        value lands on the viewport's default rather than on a 99-column grid."""
        _, cols = open_grid(NARROW, stored=99)

        assert cols == str(NARROW_COLS)


def test_the_elided_default_does_not_move_with_the_viewport():
    """`DEFAULTS.cols` is also what `writeUrl()` elides against, so it stays a
    flat 6 and the narrow value lives in `storedCols()` instead. Pushing the
    viewport term up into `DEFAULTS` would read as the tidier fix and would
    make one link mean different things on different devices -- the opposite of
    what this page's URL is for."""
    js = (STATIC / "set_browse.html").read_text()
    defaults = js[js.index("const DEFAULTS = {") : js.index("const SECTION_ORDER")]

    assert "innerWidth" not in defaults, (
        "DEFAULTS is the URL-elision anchor; the viewport term belongs in storedCols()"
    )
