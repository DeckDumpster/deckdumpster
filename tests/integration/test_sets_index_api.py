"""
Integration tests for GET /api/sets/index (de-ia6).

Runs against a live container instance with the test fixture loaded.

    bash deploy/setup.sh sets-index --test
    systemctl --user start mtgc-sets-index
    uv run pytest tests/integration/test_sets_index_api.py -v --instance sets-index

The unit tests in tests/test_set_index.py pin the counting rules and the query
plan against a synthetic database.  What only a container can show is that the
endpoint and `/api/sets` disagree about what a "set" is, and that they disagree
in the direction the binder needs.
"""

import ssl
import time
import urllib.request

#: The set index is unpaginated, so its whole cost lands on one request.  The
#: measured prod query is 39 ms over 993 sets; a second is the point at which
#: the page reads as broken rather than slow.
RESPONSE_BUDGET_MS = 1000

#: Keys the /sets page reads off every row.
ROW_KEYS = {
    "set_code", "set_name", "set_type", "released_at", "digital",
    "base_set_size", "total_set_size",
    "owned_base", "total_base", "owned_all", "total_all",
}


class TestSetsIndexPopulation:
    def test_returns_a_row_per_cached_set(self, api):
        status, data = api.get("/api/sets/index")

        assert status == 200
        assert isinstance(data, list)
        assert len(data) > 0
        codes = [row["set_code"] for row in data]
        assert len(codes) == len(set(codes))

    def test_every_row_carries_what_the_page_renders(self, api):
        status, data = api.get("/api/sets/index")

        assert status == 200
        for row in data:
            assert set(row) == ROW_KEYS

    def test_a_set_with_no_booster_config_is_present(self, api):
        """The reason this is a separate endpoint from /api/sets.

        `/api/sets` reads `mtgjson_booster_configs`, so a set you cannot open a
        pack from is silently absent from it — Commander decks, Secret Lairs,
        Special Guests.  Those sets are exactly what a binder holds, so the
        index has to reach them.  This asserts a real disagreement between the
        two endpoints, not just that some set is present.
        """
        status, index = api.get("/api/sets/index")
        assert status == 200
        status, booster = api.get("/api/sets")
        assert status == 200

        indexed = {row["set_code"] for row in index}
        with_boosters = {row["code"] for row in booster}
        missing_from_booster_sets = indexed - with_boosters

        assert missing_from_booster_sets, (
            "no cached set lacks a booster config in this fixture — the case "
            "this endpoint exists for is untested"
        )

    def test_a_set_with_no_cached_cards_is_absent(self, api):
        """`cards_fetched_at IS NULL` means there are no printings behind the row."""
        status, index = api.get("/api/sets/index")
        assert status == 200
        status, cached = api.get("/api/cached-sets")
        assert status == 200

        assert {row["set_code"] for row in index} == {row["code"] for row in cached}


class TestSetsIndexCounts:
    def test_counts_are_coherent(self, api):
        status, data = api.get("/api/sets/index")

        assert status == 200
        for row in data:
            assert 0 <= row["owned_all"] <= row["total_all"]
            if row["base_set_size"] is None:
                # 0/0 renders as NaN%, so a set with no stored boundary reports
                # no base fraction at all rather than an empty one.
                assert row["owned_base"] is None
                assert row["total_base"] is None
            else:
                assert 0 <= row["owned_base"] <= row["total_base"]
                assert row["total_base"] <= row["total_all"]

    def test_newest_release_first_and_undated_sets_last(self, api):
        status, data = api.get("/api/sets/index")

        assert status == 200
        dated = [row["released_at"] for row in data if row["released_at"]]
        undated_at = [i for i, row in enumerate(data) if not row["released_at"]]

        assert dated == sorted(dated, reverse=True)
        assert all(i >= len(dated) for i in undated_at)


class TestSetsIndexCost:
    def test_responds_well_under_a_second(self, api, base_url):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"{base_url}/api/sets/index"

        urllib.request.urlopen(url, context=ctx, timeout=30).read()  # warm
        t0 = time.perf_counter()
        urllib.request.urlopen(url, context=ctx, timeout=30).read()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < RESPONSE_BUDGET_MS, f"{elapsed_ms:.0f} ms"
