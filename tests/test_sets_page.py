"""The /sets index page: its route, and the rules its markup has to keep.

Tier 1 — no container, no network. `do_GET` reads only `self.path`, so the
dispatch table can be driven against a handler built without a socket, the way
`test_search_alias.py` does.

The page's behaviour is JavaScript and belongs to the UI scenario tests. What
is worth pinning here is the pair of facts that are invisible from either side
alone: the route exists and points at a file that exists, and that file loads
the two scripts whose globals `sets.js` calls without declaring.
"""

import inspect
from pathlib import Path
from unittest.mock import patch

from mtg_collector.cli import crack_pack_server as cps

STATIC = Path(cps.__file__).resolve().parent.parent / "static"


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
