"""/api/search is an alias of /api/collection, not a second implementation.

Tier 1 — no container, no network. Drives the real ``do_GET`` dispatch table
against a handler built without a socket, so the assertion is about routing
rather than about any particular payload.

Why this is worth pinning. /api/search was given its own handler once
(``_api_search``), and 24fc389 later pointed the route at ``_api_collection``
without deleting it. The orphan sat there for four months looking live, and was
read as live: it kept an unbounded query and a ``_bulk_attach_prices`` call that
builds an ``IN (...)`` clause holding two bound parameters per unique card in
the result — the shape de-ckq removed from /api/collection, which at catalogue
scale reached 219,952 parameters against a SQLITE_MAX_VARIABLE_NUMBER of
250,000. Nothing served it, so nothing caught it.

The defence is structural, not a budget: while one handler serves both routes,
/api/collection's page bounds and query shape are /api/search's too, and there
is no second copy to drift. A reintroduced second handler fails these tests.
"""

import inspect
from unittest.mock import patch

import pytest

from mtg_collector.cli import crack_pack_server as cps


def _bare_handler(path: str):
    """A CrackPackHandler that can dispatch, with no socket behind it.

    ``do_GET`` reads only ``self.path``, so bypassing ``__init__`` (which would
    try to serve a real request) is enough to exercise the dispatch table.
    """
    handler = object.__new__(cps.CrackPackHandler)
    handler.path = path
    return handler


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?q=lightning",
        "?q=is%3Aunowned",
        "?q=t%3Acreature&sort=cmc&order=desc",
        "?q=is%3Aunowned&limit=250&offset=500",
        "?expand=copies",
        "?cards=lci%3A150",
    ],
)
def test_search_dispatches_to_the_collection_handler(query):
    """Every /api/search request lands in _api_collection, params untouched."""
    search_handler = _bare_handler(f"/api/search{query}")
    collection_handler = _bare_handler(f"/api/collection{query}")

    with patch.object(cps.CrackPackHandler, "_api_collection") as api_collection:
        search_handler.do_GET()
        collection_handler.do_GET()

    assert api_collection.call_count == 2, "/api/search did not reach _api_collection"
    from_search, from_collection = api_collection.call_args_list
    assert from_search == from_collection, (
        "/api/search and /api/collection handed _api_collection different params"
    )


def test_there_is_no_second_search_handler():
    """No _api_search. A route needing its own handler needs its own tests too."""
    assert not hasattr(cps.CrackPackHandler, "_api_search"), (
        "_api_search is back. /api/search is served by _api_collection; a second "
        "handler drifts from it silently — that is how the unbounded query and "
        "the result-set-proportional price lookup survived four months unnoticed."
    )


def test_search_route_body_is_only_the_collection_call():
    """The dispatch branch delegates and nothing else — no pre/post-processing.

    A branch that massaged params or post-filtered the result would be a second
    implementation wearing the alias, and the dispatch test above would not see
    it.
    """
    source = inspect.getsource(cps.CrackPackHandler.do_GET)
    lines = [ln.strip() for ln in source.splitlines()]
    branch = lines.index('elif path == "/api/search":')

    statements = []
    for line in lines[branch + 1:]:
        if line.startswith(("elif ", "else:")):
            break
        if line and not line.startswith("#"):
            statements.append(line)

    assert statements == ["self._api_collection(params)"], statements
