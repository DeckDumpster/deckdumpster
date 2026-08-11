"""
Unit tests for /api/collection's limit/offset parsing.

The HTTP contract is covered by tests/integration/test_collection_paging.py;
these run in the fast tier with no container, and pin the part that decides
between a page and a 400.
"""

import pytest

from mtg_collector.cli.crack_pack_server import (
    COLLECTION_LIMIT_DEFAULT,
    COLLECTION_LIMIT_MAX,
    PageParamError,
    _parse_page_params,
)


def _params(**kw):
    """Query params in the shape parse_qs hands the handler."""
    return {k: [str(v)] for k, v in kw.items()}


class TestDefaults:
    def test_absent_params_are_bounded(self):
        assert _parse_page_params({}) == (COLLECTION_LIMIT_DEFAULT, 0)

    def test_blank_params_fall_back_to_defaults(self):
        assert _parse_page_params(_params(limit="", offset="")) == (COLLECTION_LIMIT_DEFAULT, 0)


class TestAccepted:
    @pytest.mark.parametrize("limit", [1, 250, COLLECTION_LIMIT_MAX])
    def test_limit_in_range(self, limit):
        assert _parse_page_params(_params(limit=limit)) == (limit, 0)

    def test_offset(self):
        assert _parse_page_params(_params(limit=10, offset=990)) == (10, 990)

    def test_offset_may_run_past_the_end(self):
        """A too-large offset is an empty page, not an error — the caller
        cannot know the total before asking."""
        assert _parse_page_params(_params(offset=10**9)) == (COLLECTION_LIMIT_DEFAULT, 10**9)


class TestRejected:
    """Out-of-range is a 400, never a silent clamp — a clamped limit would let
    a caller believe it had walked the whole result."""

    @pytest.mark.parametrize(
        "kw",
        [
            {"limit": COLLECTION_LIMIT_MAX + 1},
            {"limit": 0},
            {"limit": -1},
            {"limit": "abc"},
            {"limit": "1.5"},
            {"limit": "250; DROP TABLE collection"},
            {"offset": -1},
            {"offset": "abc"},
        ],
    )
    def test_raises(self, kw):
        with pytest.raises(PageParamError):
            _parse_page_params(_params(**kw))
