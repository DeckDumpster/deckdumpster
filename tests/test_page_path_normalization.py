"""A trailing slash on a page path is not a request for a child called nothing.

Tier 1 -- no container, no network.  `do_GET` reads only `self.path`, so the
dispatch table can be driven against a handler built without a socket, the way
`test_sets_page.py` does.

`/sets/` used to serve the binder grid for a set whose code was the empty
string: a page titled "Browse Set" whose only content was the endpoint's
"Set '' not cached (run `mtg cache all` to populate)".  Both halves were wrong,
and the second was expensively wrong -- it named the catalogue as the cause on
an evening the catalogue had just been rebuilt by hand, so it sent everyone to
the wrong place first.

These assert the behaviour -- which page is served, what the endpoint answers --
never the shape of the dispatch that produces it.
"""

from unittest.mock import patch

import pytest

from mtg_collector.cli import crack_pack_server as cps


def _bare_handler(path: str):
    handler = object.__new__(cps.CrackPackHandler)
    handler.path = path
    return handler


def _page_served(path: str) -> str:
    """The static file `path` serves, whichever of the two serve helpers ran."""
    handler = _bare_handler(path)
    with patch.object(cps.CrackPackHandler, "_serve_static") as plain, \
         patch.object(cps.CrackPackHandler, "_serve_static_with_data") as with_data:
        handler.do_GET()
    calls = plain.call_args_list + with_data.call_args_list
    assert len(calls) == 1, f"{path} served {len(calls)} pages"
    return calls[0].args[0]


def test_sets_with_a_trailing_slash_is_the_index():
    assert _page_served("/sets/") == "sets.html"


def test_a_set_code_still_reaches_the_binder():
    """The normalisation must not swallow the page it is protecting."""
    assert _page_served("/sets/lci") == "set_browse.html"


def test_a_trailing_slash_after_a_set_code_is_still_that_set():
    assert _page_served("/sets/lci/") == "set_browse.html"


@pytest.mark.parametrize("path,expected", [
    ("/sets/", "sets.html"),
    ("/decks/", "decks.html"),
    ("/orders/", "orders.html"),
    ("/batches/", "batches.html"),
    ("/corner-batches/", "batches.html"),
])
def test_every_parent_route_owns_its_trailing_slash(path, expected):
    """The hole is the shape `path == X` for the parent and `startswith(X + "/")`
    for the child, which is every one of these -- so the fix is one rule rather
    than a guard bolted onto `/sets`."""
    assert _page_served(path) == expected


def test_the_homepage_is_not_normalised_away():
    """`_normalize_page_path` must never turn `/` into `""` -- an empty path
    would fall through every route in the table (see de-j19: routing is a
    single PAGE_ROUTES table now, `/` has no dedicated serve method to patch,
    so this asserts what actually gets served)."""
    assert _page_served("/") == "index.html"


def test_a_query_string_does_not_defeat_the_normalisation():
    assert _page_served("/sets/?cols=3") == "sets.html"


class TestTheEmptyCodeError:
    """`/api/set-browse/` keeps reaching its handler so it can name the code.

    Normalising the API path away would answer with a bare 404 "Not found",
    which is not wrong but says nothing.  The endpoint knows what was asked for
    and can say so.
    """

    def _answer(self, path: str):
        handler = _bare_handler(path)
        with patch.object(cps.CrackPackHandler, "_send_json") as send:
            handler.do_GET()
        send.assert_called_once()
        payload, status = send.call_args.args
        return status, payload

    def test_an_empty_code_is_a_400(self):
        status, _payload = self._answer("/api/set-browse/")

        assert status == 400

    def test_the_empty_code_error_does_not_blame_the_cache(self):
        """The load-bearing half.  "run `mtg cache all` to populate" is a
        plausible, trusted, wrong cause for a URL with no set code in it, and an
        error that is trusted and wrong costs more than a generic one."""
        _status, payload = self._answer("/api/set-browse/")

        assert "cache" not in payload["error"].lower()
        assert "set code" in payload["error"].lower()

    @pytest.mark.parametrize("code", ["ab c", "lci/extra", "l.c"])
    def test_a_code_that_cannot_name_a_set_is_the_same_400(self, code):
        status, payload = self._answer(f"/api/set-browse/{code}")

        assert status == 400
        assert "cache" not in payload["error"].lower()


class TestTheCacheMessageSurvives:
    """It is the right answer for a code that could name a set and does not --
    only that case, and still that case."""

    def test_a_well_formed_code_gets_past_the_code_check(self):
        assert cps._parse_set_code("ZZZ") == "zzz"

    @pytest.mark.parametrize("code", ["lci", "10e", "4bb", "plist", "unfin1"])
    def test_real_set_code_shapes_are_well_formed(self, code):
        """Codes have grown from three characters to six and mix digits in, so
        the check is alphanumeric with no length bound -- a cap would reject a
        real set as malformed."""
        assert cps._parse_set_code(code) == code
