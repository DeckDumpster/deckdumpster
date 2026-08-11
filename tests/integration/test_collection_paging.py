"""
Paging contract for /api/collection.

The endpoint returns a page envelope — {rows, total, limit, offset} — never a
bare array.  `limit` defaults to 250 and caps at 1000; there is no unbounded
escape hatch and no sentinel, so every caller takes the same semantics.  A bad
`limit` or `offset` is a 400, not a silent clamp.

Usage:
    uv run pytest tests/integration/test_collection_paging.py -v --instance <instance>
"""

import json

import pytest

DEFAULT_LIMIT = 250
MAX_LIMIT = 1000

# The three query templates behind /api/collection: aggregated default,
# one-row-per-copy (deck-builder picker), and the LEFT-JOIN unowned template.
TEMPLATES = [
    pytest.param("", id="default"),
    pytest.param("expand=copies", id="expand-copies"),
    pytest.param("q=is%3Aunowned", id="is-unowned"),
]


def _page(api, query: str, **page_params):
    """GET one page, asserting the envelope shape. Returns the parsed body."""
    parts = [p for p in [query, *(f"{k}={v}" for k, v in page_params.items())] if p]
    path = "/api/collection" + ("?" + "&".join(parts) if parts else "")
    status, body = api.get(path)
    assert status == 200, f"{path} -> {status} {body}"
    assert isinstance(body, dict), f"{path} returned a bare {type(body).__name__}, not an envelope"
    assert set(body) >= {"rows", "total", "limit", "offset"}, f"{path} envelope keys: {sorted(body)}"
    assert isinstance(body["rows"], list)
    return body


def _identity(row: dict) -> str:
    """Stable identity for a result row, for gap/duplicate detection."""
    return json.dumps(row, sort_keys=True)


class TestPageEnvelope:
    @pytest.mark.parametrize("query", TEMPLATES)
    def test_default_page_is_bounded(self, api, query):
        """No paging params: 250 rows at offset 0, with an honest total."""
        body = _page(api, query)

        assert body["limit"] == DEFAULT_LIMIT
        assert body["offset"] == 0
        assert len(body["rows"]) <= DEFAULT_LIMIT
        assert body["total"] >= len(body["rows"])

    @pytest.mark.parametrize("query", TEMPLATES)
    def test_limit_bounds_the_page(self, api, query):
        """`limit` caps the rows returned without changing `total`."""
        unbounded_total = _page(api, query)["total"]
        body = _page(api, query, limit=2)

        assert body["limit"] == 2
        assert len(body["rows"]) <= 2
        assert body["total"] == unbounded_total, "total must count the whole result, not the page"

    @pytest.mark.parametrize("query", TEMPLATES)
    def test_total_is_the_unbounded_count(self, api, query):
        """`total` is independent of the page size."""
        assert _page(api, query, limit=1)["total"] == _page(api, query, limit=MAX_LIMIT)["total"]

    def test_max_limit_is_accepted(self, api):
        body = _page(api, "", limit=MAX_LIMIT)
        assert body["limit"] == MAX_LIMIT

    @pytest.mark.parametrize("query", TEMPLATES)
    def test_total_agrees_on_every_page_of_a_walk(self, api, query):
        """A short page lets the server infer the total instead of counting it.

        The inference and the count must agree, including on the last page of
        a walk (short, non-zero offset) and past the end (empty, so the offset
        proves nothing) — those take different branches.
        """
        counted = _page(api, query, limit=1)["total"]
        if counted == 0:
            pytest.skip("no rows for this query in the fixture dataset")

        page_size = 3
        last_offset = (counted - 1) // page_size * page_size
        for offset in (0, last_offset, counted, counted + 5):
            body = _page(api, query, limit=page_size, offset=offset)
            assert body["total"] == counted, f"total disagrees at offset={offset}"


class TestOffsetWalk:
    @pytest.mark.parametrize("query", TEMPLATES)
    def test_walk_has_no_gaps_or_repeats(self, api, query):
        """Paging by offset visits every row exactly once.

        This is what a non-total ORDER BY breaks: ties at a page boundary drop
        and duplicate rows, which reads as data loss rather than a bug.
        """
        first = _page(api, query, limit=1)
        total = first["total"]
        if total == 0:
            pytest.skip("no rows for this query in the fixture dataset")
        # Keep the walk bounded — a full catalog walk is not the point here.
        walk_total = min(total, 40)
        page_size = 3

        seen: list[str] = []
        for offset in range(0, walk_total, page_size):
            body = _page(api, query, limit=page_size, offset=offset)
            assert body["offset"] == offset
            assert body["total"] == total, "total drifted mid-walk"
            seen.extend(_identity(r) for r in body["rows"])

        expected = min(walk_total + (-walk_total % page_size), total)
        assert len(seen) == expected, "walk returned the wrong number of rows"
        assert len(set(seen)) == len(seen), "walk returned duplicate rows"

        # Same rows as reading the range in one page — no drops at boundaries.
        one_shot = _page(api, query, limit=expected, offset=0)["rows"]
        assert [_identity(r) for r in one_shot] == seen, "paged order differs from single-page order"

    def test_offset_past_the_end_is_an_empty_page(self, api):
        """Past the end is an empty page with an honest total, not an error."""
        total = _page(api, "")["total"]
        body = _page(api, "", limit=10, offset=total + 10)

        assert body["rows"] == []
        assert body["total"] == total
        assert body["offset"] == total + 10


class TestRejectsBadPaging:
    """A bad limit/offset is a 400, never a silent clamp."""

    @pytest.mark.parametrize(
        "params",
        [
            "limit=1001",
            "limit=-1",
            "limit=abc",
            "limit=0",
            "limit=1.5",
            "offset=-1",
            "offset=abc",
        ],
    )
    def test_rejected_with_400(self, api, params):
        status, body = api.get(f"/api/collection?{params}")

        assert status == 400, f"?{params} -> {status} {body}"
        assert "error" in body
