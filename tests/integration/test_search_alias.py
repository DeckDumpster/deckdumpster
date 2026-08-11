"""/api/search returns exactly what /api/collection returns, over the wire.

The unit-tier companion (tests/test_search_alias.py) pins the dispatch. This
pins the observable consequence: for the same query string the two routes are
indistinguishable — same status, same bytes. Whatever bounds, ordering and
response envelope /api/collection has, /api/search has, without /api/search
being named in that work.

That is the whole defence against the drift that produced de-33j: a route with
its own handler acquired an unbounded query and a price lookup whose bound
parameter count grew with the result set, and no test noticed because nothing
served it. A single handler cannot drift from itself.

Bodies are compared as raw bytes rather than parsed JSON: it is the stricter
assertion, and it keeps the is:unowned case (109,976 rows / 96.96 MB against a
full catalogue) from parsing a 97 MB document twice to answer a question about
equality.

Usage:
    uv run pytest tests/integration/test_search_alias.py -v --instance <instance>
"""

import hashlib

import pytest

# Between them these reach all three /api/collection query templates (aggregated
# default, is:unowned LEFT JOIN, expand=copies), the sort path, the
# explicit-card-list path, and the parse-error path.
QUERIES = [
    "",
    "?q=lightning",
    "?q=is%3Aunowned",
    "?q=t%3Acreature",
    "?q=t%3Acreature&sort=cmc&order=desc",
    "?q=r%3Arare&sort=name&order=asc",
    "?expand=copies",
    "?q=status%3Aowned",
    "?q=%28",  # malformed — must be the same 400 with the same error body
]


def _fetch(api, path):
    status, body = api.get_raw(path)
    return status, hashlib.sha256(body).hexdigest(), len(body)


@pytest.mark.parametrize("query", QUERIES)
def test_search_and_collection_are_byte_identical(api, query):
    search = _fetch(api, f"/api/search{query}")
    collection = _fetch(api, f"/api/collection{query}")

    assert search[0] == collection[0], (
        f"/api/search{query} -> HTTP {search[0]} but "
        f"/api/collection{query} -> HTTP {collection[0]}"
    )
    assert search == collection, (
        f"/api/search{query} and /api/collection{query} returned different bodies "
        f"({search[2]} vs {collection[2]} bytes); the routes have drifted apart"
    )


def test_malformed_query_is_a_400_on_both_routes(api):
    """Keeps the parametrised malformed case honest.

    Two matching 200s would satisfy byte-identity while proving the error path
    is not an error path at all.
    """
    for route in ("/api/search", "/api/collection"):
        status, body = api.get(f"{route}?q=%28")
        assert status == 400, f"{route} accepted a malformed query ({status})"
        assert "error" in body


@pytest.mark.parametrize("query", ["", "?q=is%3Aunowned"])
def test_search_response_shape_matches_collection(api, query):
    """The response *type* matches too, not merely the bytes.

    A caller that maps over the result breaks silently if one route grows a page
    envelope and the other stays a bare array — it renders empty rather than
    throwing, which reads as data loss. This holds whichever shape is current.
    """
    _, search_body = api.get(f"/api/search{query}")
    _, coll_body = api.get(f"/api/collection{query}")

    assert type(search_body) is type(coll_body)
    if isinstance(search_body, dict):
        assert search_body.keys() == coll_body.keys()
