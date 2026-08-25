"""The /sets index page: its route, and the rules its markup has to keep.

Tier 1 — no container, no network. `do_GET` reads only `self.path`, so the
dispatch table can be driven against a handler built without a socket, the way
`test_search_alias.py` does.

Most of the page's behaviour is JavaScript and belongs to the UI scenario
tests. What is worth pinning here is what is invisible from either side alone:
the route exists and points at a file that exists, that file loads the two
scripts whose globals `sets.js` calls without declaring, the group order is
what `SET_TYPE_RANK` says rather than what the payload happened to arrive in,
and the completion sort orders by the fraction rather than by the count.

Those last two are here and not in `tests/ui/` on purpose. A scenario test runs
against the fixture database, and the fixture's newest set is an expansion — so
it reads Expansion-first whether the rank exists or not, and its owned counts
are whatever the demo data happens to hold rather than the pairs that separate
a percentage sort from a count sort. Both invariants only show up against a
payload no fixture will produce, so these drive the real page (real
`sets.html`, real scripts, `/api/sets/index` answered synthetically) in a
browser and read the order back out of the DOM.

The jump rail and the collapsible groups are pinned here for the same reason,
plus one more: the narrow-viewport form is a `@media` rule, and the only way to
assert it is to size a viewport at it. That is a browser fixture's job, not a
container scenario's.
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


def _set(code, set_type, released_at, name=None, owned_all=0, total_all=120):
    """One row of `/api/sets/index`. The group-order tests care only about the
    type and the date; the completion-sort tests drive `owned_all` / `total_all`,
    which is the fraction that sort reads."""
    return {
        "set_code": code,
        "set_name": name or code.upper(),
        "set_type": set_type,
        "released_at": released_at,
        "owned_base": 0,
        "total_base": 100,
        "owned_all": owned_all,
        "total_all": total_all,
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

    def load(payload, viewport=None):
        page = browser.new_page(viewport=viewport) if viewport else browser.new_page()
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


def _owned(row, owned_all):
    """The same index row with cards in hand, for the group roll-up."""
    return {**row, "owned_all": owned_all}


def _rail(page):
    return page.eval_on_selector_all(
        "#sets-rail .rail-row",
        "els => els.map(e => [e.dataset.setType, e.querySelector('.rail-count').textContent])",
    )


def _grid_visible(page, set_type):
    return page.locator(f"section[data-set-type='{set_type}'] .set-grid").is_visible()


def test_the_rail_lists_the_groups_in_rank_order_with_their_counts(load_sets):
    """The rail is built from the same array the sections are, so its rows are
    the rendered groups, in the rendered order — a type the rank has never heard
    of gets its row at the end for free, and no row can name a section that is
    not on the page to jump to."""
    page, order, errors = load_sets(
        [
            _set("newt", "some_future_type", "2026-08-24"),
            _set("tok1", "token", "2026-08-20"),
            _set("tok2", "token", "2026-08-19"),
            _set("expn", "expansion", "2026-01-23"),
        ]
    )

    assert errors == []
    assert _rail(page) == [
        ["expansion", "1"],
        ["token", "2"],
        ["some_future_type", "1"],
    ]
    # And it is the section order, not a second opinion about it.
    assert [row[0] for row in _rail(page)] == order


def test_only_the_top_four_ranked_types_start_expanded(load_sets):
    """Expansion, Core, Commander, Masters — 211 of ~995 sets at prod scale.
    Explicitly not collapse-unless-owned: that rule would also expand Token and
    Promo, which between them are over half the catalogue."""
    page, _, errors = load_sets(
        [
            _set("expn", "expansion", "2026-01-23"),
            _set("core", "core", "2025-11-14"),
            _set("cmdr", "commander", "2025-09-26"),
            _set("mstr", "masters", "2025-06-13"),
            _set("draf", "draft_innovation", "2025-04-11"),
            _set("tokn", "token", "2025-02-07"),
        ]
    )

    assert errors == []
    for set_type in ("expansion", "core", "commander", "masters"):
        assert _grid_visible(page, set_type), f"{set_type} should start expanded"
    for set_type in ("draft_innovation", "token"):
        assert not _grid_visible(page, set_type), f"{set_type} should start collapsed"
    # Collapsed is a class on the section, never a removal: the tiles are still
    # in the DOM, which is what lets the filter below reach into them.
    assert page.locator("a.set-tile").count() == 6


def test_a_group_header_toggles_its_own_group(load_sets):
    page, _, errors = load_sets(
        [_set("expn", "expansion", "2026-01-23"), _set("tokn", "token", "2025-02-07")]
    )

    page.click("section[data-set-type='token'] h2")
    assert _grid_visible(page, "token")
    assert _grid_visible(page, "expansion"), "the other groups keep their own state"

    page.click("section[data-set-type='token'] h2")
    assert not _grid_visible(page, "token")
    assert errors == []


def test_a_rail_row_expands_its_group_and_scrolls_to_it(load_sets):
    """The rail's whole job. Token starts collapsed and is at the bottom of a
    page tall enough to scroll, so both halves are observable."""
    page, _, errors = load_sets(
        [_set(f"e{i:03d}", "expansion", "2026-01-23") for i in range(30)]
        + [_set("tokn", "token", "2025-02-07")]
    )

    assert not _grid_visible(page, "token")
    assert page.evaluate("window.scrollY") == 0

    page.click("#sets-rail .rail-row[data-set-type='token']")

    assert _grid_visible(page, "token")
    # scrollIntoView is smooth, so the scroll lands a frame or two later.
    page.wait_for_function("() => window.scrollY > 0")
    assert errors == []


def test_a_filter_match_inside_a_collapsed_group_opens_it(load_sets):
    """The count and the page have to agree. Filtering to a set that lives in a
    collapsed group used to be reachable only by expanding the group by hand —
    the header would read "1 of 2 sets" over a page showing none of them."""
    page, _, errors = load_sets(
        [
            _set("expn", "expansion", "2026-01-23", name="Lorwyn Eclipsed"),
            _set("tokn", "token", "2025-02-07", name="Tarkir Tokens"),
        ]
    )

    assert not _grid_visible(page, "token")

    page.fill("#set-filter", "tarkir")

    assert _grid_visible(page, "token")
    assert page.locator("a.set-tile[href='/sets/tokn']").is_visible()
    assert page.locator("section[data-set-type='expansion']").is_hidden()
    assert page.locator("#sets-count").text_content() == "1 of 2 sets"

    # Clearing the filter hands every group back to the state it was in.
    page.fill("#set-filter", "")
    assert not _grid_visible(page, "token")
    assert _grid_visible(page, "expansion")
    assert errors == []


def test_the_filter_matches_each_tile_against_its_own_set(load_sets):
    """The tiles are paired with their sets per group, not by one running index
    over every tile on the page. A drifting index shows the neighbouring set's
    tile for a match, which reads as a filter that is merely fuzzy — so the
    assertion is *which* tile survived, in the last group, past a collapsed one."""
    page, _, errors = load_sets(
        [
            _set("aaa", "expansion", "2026-01-23", name="Alpha"),
            _set("bbb", "expansion", "2026-01-22", name="Bravo"),
            _set("ccc", "token", "2025-02-07", name="Charlie"),
            _set("ddd", "promo", "2025-01-06", name="Delta"),
            _set("eee", "promo", "2025-01-05", name="Echo"),
        ]
    )

    page.fill("#set-filter", "echo")

    visible = page.eval_on_selector_all(
        "a.set-tile:not([hidden])", "els => els.map(e => e.getAttribute('href'))"
    )
    assert visible == ["/sets/eee"]
    assert page.locator("#sets-count").text_content() == "1 of 5 sets"
    # The rail recounts with the sections, and says which rows go nowhere.
    assert _rail(page) == [["expansion", "0"], ["token", "0"], ["promo", "1"]]
    assert page.locator("#sets-rail .rail-row.is-empty").count() == 2
    assert errors == []


def test_the_group_roll_up_counts_the_sets_with_cards_in_hand(load_sets):
    """The header's second number: how many of the group's sets you have any
    card from. It tracks the filter the way the count beside it does, so the
    header always describes what is on screen."""
    page, _, errors = load_sets(
        [
            _owned(_set("aaa", "expansion", "2026-01-23", name="Alpha"), 12),
            _owned(_set("bbb", "expansion", "2026-01-22", name="Bravo"), 3),
            _set("ccc", "expansion", "2026-01-21", name="Charlie"),
        ]
    )

    roll_up = page.locator("section[data-set-type='expansion'] .group-owned")
    assert roll_up.text_content() == "2 owned"

    page.fill("#set-filter", "charlie")
    assert roll_up.text_content() == "0 owned"
    assert errors == []


def test_the_narrow_viewport_form_ships_with_the_rail(load_sets):
    """de-l5l is the live evidence this codebase forgets the `@media` half of a
    layout change, so it is asserted in the same change. At 700px and under the
    two columns become one and the rail stops being sticky — the same collapse
    deck-builder.css does — and the rail's rows wrap as chips rather than
    standing 24 tall above the first set tile."""
    payload = [
        _set("expn", "expansion", "2026-01-23"),
        _set("tokn", "token", "2025-02-07"),
    ]

    wide, _, errors = load_sets(payload, viewport={"width": 1280, "height": 720})
    assert errors == []
    assert len(wide.eval_on_selector(
        ".sets-layout", "el => getComputedStyle(el).gridTemplateColumns"
    ).split()) == 2
    assert wide.eval_on_selector(".sets-rail", "el => getComputedStyle(el).position") == "sticky"

    narrow, _, errors = load_sets(payload, viewport={"width": 390, "height": 844})
    assert errors == []
    assert len(narrow.eval_on_selector(
        ".sets-layout", "el => getComputedStyle(el).gridTemplateColumns"
    ).split()) == 1
    assert narrow.eval_on_selector(".sets-rail", "el => getComputedStyle(el).position") == "static"
    assert narrow.eval_on_selector(
        ".rail-list", "el => getComputedStyle(el).flexDirection"
    ) == "row"
    # And the rail is still the whole rail — the narrow form folds no rows away.
    assert [row[0] for row in _rail(narrow)] == ["expansion", "token"]
# --- Completion sort (de-kbq) ---------------------------------------------
#
# The select is the only question on this page that grouping cannot answer:
# which sets am I close to finishing. Those live in the DOM order the sort
# produces, so these read the tiles back out of the browser the same way the
# group-order tests do.


def _codes_in_order(page):
    """Set codes of the visible tiles, in document order."""
    return page.eval_on_selector_all(
        "#sets-body a.set-tile:not([hidden])",
        "els => els.map(e => e.href.split('/').pop())",
    )


def _choose_completion(page):
    page.select_option("#sets-sort", "completion")
    page.wait_for_selector("#sets-body section[data-sort='completion']")


def test_release_date_is_the_default_sort(load_sets):
    """The select exists, and the page it renders before anyone touches it is
    the grouped one — a page that opened in completion mode would hide every
    set nothing is owned from, which is most of them."""
    page, _, errors = load_sets([_set("expn", "expansion", "2026-01-23", owned_all=5)])

    assert page.locator("#sets-sort").input_value() == "released"
    assert page.locator("#sets-body section[data-set-type]").count() == 1
    assert page.locator("#sets-body section[data-sort='completion']").count() == 0
    assert errors == []


def test_completion_sort_orders_by_percentage_not_by_count(load_sets):
    """The fraction is what is being sorted, so a set with 9 of 10 leads one
    with 60 of 120. Sorting on `owned_all` alone — the tempting shortcut, since
    it needs no division — reverses exactly this pair."""
    page, _, errors = load_sets(
        [
            _set("half", "expansion", "2026-08-24", owned_all=60, total_all=120),
            _set("near", "commander", "2026-08-20", owned_all=9, total_all=10),
            _set("thin", "token", "2026-08-15", owned_all=1, total_all=50),
        ]
    )
    _choose_completion(page)

    assert _codes_in_order(page) == ["near", "half", "thin"]
    assert errors == []


def test_completion_sort_drops_the_sets_nothing_is_owned_from(load_sets):
    """`owned_all > 0` is the population. A set at 0 / 291 is not a set you are
    close to finishing, and at prod scale 860 of the 993 are exactly that —
    they would all tie for last and bury the answer under empty tiles."""
    page, _, errors = load_sets(
        [
            _set("emty", "expansion", "2026-08-24", owned_all=0, total_all=291),
            _set("some", "expansion", "2026-08-20", owned_all=4, total_all=100),
            _set("nada", "commander", "2026-08-15", owned_all=0, total_all=50),
        ]
    )
    _choose_completion(page)

    assert _codes_in_order(page) == ["some"]
    assert page.locator("#sets-count").text_content() == "1 sets"
    assert errors == []


def test_completion_sort_dissolves_the_set_type_grouping(load_sets):
    """One flat grid, not one grid per type: the sets you are closest to are
    spread across every type, so keeping the sections is what hides the answer.
    Switching back restores them."""
    page, _, errors = load_sets(
        [
            _set("expn", "expansion", "2026-08-24", owned_all=10, total_all=100),
            _set("cmdr", "commander", "2026-08-20", owned_all=50, total_all=100),
            _set("tokn", "token", "2026-08-15", owned_all=90, total_all=100),
        ]
    )
    _choose_completion(page)

    assert page.locator("#sets-body section[data-set-type]").count() == 0
    assert page.locator("#sets-body section").count() == 1
    assert _codes_in_order(page) == ["tokn", "cmdr", "expn"]

    page.select_option("#sets-sort", "released")
    page.wait_for_selector("#sets-body section[data-set-type]")
    assert page.locator("#sets-body section[data-set-type]").count() == 3
    assert errors == []


def test_the_filter_survives_a_sort_change(load_sets):
    """The two controls are independent: switching sort re-renders the body,
    and the filter text is still in an input that re-render does not touch."""
    page, _, errors = load_sets(
        [
            _set("fin", "expansion", "2026-08-24", name="Final Fantasy", owned_all=10, total_all=100),
            _set("cmdr", "commander", "2026-08-20", name="Commander", owned_all=50, total_all=100),
        ]
    )
    page.fill("#set-filter", "final")
    _choose_completion(page)

    assert _codes_in_order(page) == ["fin"]
    assert page.locator("#sets-count").text_content() == "1 of 2 sets"
    assert errors == []


def test_the_filter_still_works_after_switching_back_and_forth(load_sets):
    """Each render rebuilds the pass that hides tiles, and a keystroke after
    several switches has to drive the tiles now on the page — a render that
    left `apply` pointing at an earlier one would filter a detached grid and
    the visible tiles would never move."""
    page, _, errors = load_sets(
        [
            _set("fin", "expansion", "2026-08-24", name="Final Fantasy", owned_all=10, total_all=100),
            _set("cmdr", "commander", "2026-08-20", name="Commander", owned_all=50, total_all=100),
        ]
    )
    _choose_completion(page)
    page.select_option("#sets-sort", "released")
    page.wait_for_selector("#sets-body section[data-set-type]")
    _choose_completion(page)

    page.fill("#set-filter", "commander")
    page.dispatch_event("#set-filter", "input")

    assert _codes_in_order(page) == ["cmdr"]
    assert page.locator("#sets-count").text_content() == "1 of 2 sets"
    assert errors == []


def test_completion_mode_says_so_when_nothing_is_owned(load_sets):
    """A fresh install has cached sets and an empty collection. The grid says
    that rather than rendering nothing, and it does not also claim the filter
    is what emptied it."""
    page, _, errors = load_sets(
        [
            _set("expn", "expansion", "2026-08-24", owned_all=0),
            _set("cmdr", "commander", "2026-08-20", owned_all=0),
        ]
    )
    page.select_option("#sets-sort", "completion")
    page.wait_for_selector("#sets-body .empty-state:not([hidden])")

    assert "Nothing is owned" in page.locator("#sets-body .empty-state").first.text_content()
    assert page.locator("#sets-no-match").is_hidden()
    assert page.locator("#sets-count").text_content() == "0 sets"
    assert errors == []


def test_the_sort_select_is_in_the_page(load_sets):
    """Both options, with the values sets.js branches on. A renamed value would
    silently fall through to the grouped render."""
    html = (STATIC / "sets.html").read_text()
    assert 'id="sets-sort"' in html
    assert 'value="released"' in html
    assert 'value="completion"' in html
