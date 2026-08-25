"""The binder contract for /api/set-browse/:set_code, over HTTP.

Before this, the endpoint returned a bare JSON array with one row per *copy*.
Measured against prod on the six most heavily owned sets, the inflation ran
1.19x to 2.41x -- `sos` handed back 888 rows for 368 printings, so a binder
rendered from it showed the same pocket two or three times, and there was no
`qty` field anywhere to tell you it had.

The fixture this runs against has an empty `collection` table, so the fan-out is
invisible until copies are seeded; the tests below seed their own.

Usage:
    uv run pytest tests/integration/test_set_browse_api.py -v --instance <instance>
"""

import pytest

MAX_LIMIT = 1000
DEFAULT_LIMIT = 250

#: How many copies of one printing to seed. 2.41x was prod's worst measured
#: inflation, so three copies of a printing reproduces it and then some.
COPIES = 3


def _browse(api, set_code, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path = f"/api/set-browse/{set_code}" + (f"?{query}" if query else "")
    status, body = api.get(path)
    assert status == 200, f"{path} -> {status} {body}"
    assert isinstance(body, dict), f"{path} returned a bare {type(body).__name__}, not an envelope"
    assert set(body) >= {"rows", "total", "limit", "offset"}, f"{path} envelope keys: {sorted(body)}"
    return body


@pytest.fixture(scope="module")
def browsable_set(api):
    """A cached set with enough printings to page, and its printing count."""
    status, sets = api.get("/api/cached-sets")
    assert status == 200, sets

    for entry in sets:
        body = _browse(api, entry["code"], limit=1, sections="base,extended,promo")
        if body["total"] > DEFAULT_LIMIT:
            return entry["code"], body["total"]
    pytest.skip("no cached set with more than one page of printings")


@pytest.fixture(scope="module")
def owned_set(api, browsable_set):
    """The same set, with several copies of its first three printings held.

    Module-scoped: the copies are the point of every test here.  They are
    removed again afterwards rather than left for the suite's session-scoped
    restore, so this file cannot move another file's numbers by running first.
    """
    set_code, total = browsable_set
    rows = _browse(api, set_code, limit=10, sections="base,extended,promo")["rows"]

    added_ids = []
    for row in rows[:3]:
        for _ in range(COPIES):
            status, added = api.post("/api/collection", {
                "printing_id": row["printing_id"],
                "finish": row["finishes"][0] if row["finishes"] else "nonfoil",
            })
            assert status == 200, added
            added_ids.append(added["id"])

    yield set_code, total

    for entry_id in added_ids:
        api.delete(f"/api/collection/{entry_id}")


class TestOneRowPerPrinting:
    def test_copies_do_not_inflate_the_row_count(self, api, owned_set):
        """The regression guard on the 2.41x fan-out."""
        set_code, total = owned_set

        body = _browse(api, set_code, limit=MAX_LIMIT, sections="base,extended,promo")

        assert len(body["rows"]) == min(total, MAX_LIMIT)
        assert len({r["printing_id"] for r in body["rows"]}) == len(body["rows"])

    def test_the_held_printings_report_their_copies(self, api, owned_set):
        set_code, _total = owned_set

        rows = _browse(api, set_code, limit=10, sections="base,extended,promo")["rows"]

        assert [r["qty"] for r in rows[:3]] == [COPIES] * 3
        for row in rows[:3]:
            assert sum(o["qty"] for o in row["owned"]) == row["qty"]

    def test_an_offset_walk_repeats_no_printing(self, api, owned_set):
        """Paging a result whose rows were copies dropped and duplicated cards."""
        set_code, total = owned_set
        limit, offset, seen = 100, 0, []

        while offset < total:
            page = _browse(api, set_code, limit=limit, offset=offset,
                           sections="base,extended,promo")
            seen += [r["printing_id"] for r in page["rows"]]
            if len(page["rows"]) < limit:
                break
            offset += limit

        assert len(seen) == total
        assert len(set(seen)) == len(seen)


class TestEnvelope:
    def test_the_header_and_meters_come_with_the_first_window(self, api, owned_set):
        set_code, _total = owned_set

        body = _browse(api, set_code, limit=MAX_LIMIT)

        assert body["set"]["set_code"] == set_code
        assert set(body["set"]) == {
            "set_code", "set_name", "released_at", "base_set_size", "total_set_size",
        }
        assert body["owned_all"] >= 3
        assert body["total_all"] >= body["total"]

    def test_later_windows_omit_them_rather_than_going_stale(self, api, owned_set):
        set_code, _total = owned_set

        body = _browse(api, set_code, limit=10, offset=10)

        assert "set" not in body
        assert "owned_all" not in body

    @pytest.mark.parametrize("view", [
        {"filter": "need"},
        {"filter": "have"},
        {"sections": "base"},
        {"q": "a"},
    ])
    def test_the_meters_do_not_move_when_the_view_is_filtered(self, api, owned_set, view):
        set_code, _total = owned_set
        meters = ("owned_base", "total_base", "owned_all", "total_all")
        unfiltered = _browse(api, set_code, limit=MAX_LIMIT)

        filtered = _browse(api, set_code, limit=MAX_LIMIT, **view)

        assert [filtered[k] for k in meters] == [unfiltered[k] for k in meters]

    def test_the_default_page_is_bounded(self, api, owned_set):
        """Defect 2: fin serialised to 743 KiB as one unbounded array."""
        set_code, total = owned_set

        body = _browse(api, set_code)

        assert body["limit"] == DEFAULT_LIMIT
        assert len(body["rows"]) == DEFAULT_LIMIT
        assert body["total"] == total or body["total"] >= DEFAULT_LIMIT


class TestBadParams:
    """A bad param is a 400, never a silent clamp -- a clamped limit would let a
    caller believe it had walked the whole set."""

    @pytest.mark.parametrize("params", [
        {"limit": 0},
        {"limit": MAX_LIMIT + 1},
        {"limit": "abc"},
        {"offset": -1},
        {"sort": "collector"},
        {"order": "ascending"},
        {"filter": "owned"},
        {"sections": "base,bogus"},
    ])
    def test_rejected(self, api, browsable_set, params):
        set_code, _total = browsable_set
        query = "&".join(f"{k}={v}" for k, v in params.items())

        status, body = api.get(f"/api/set-browse/{set_code}?{query}")

        assert status == 400, f"{params} -> {status} {body}"
        assert "error" in body

    def test_an_uncached_set_is_still_a_404(self, api):
        """The cache message is the right answer for a code that could name a
        set and does not, and it stays that answer."""
        status, body = api.get("/api/set-browse/zzz")

        assert status == 404
        assert "not cached" in body["error"]
        assert "mtg cache all" in body["error"]

    def test_an_empty_code_is_a_400_that_does_not_blame_the_cache(self, api):
        """`/api/set-browse/` is a URL with no set code in it, so nothing is
        uncached.  Answering "run `mtg cache all` to populate" names a cause
        that is plausible, trusted and wrong, and sends the reader to the
        catalogue while the fault is in the URL."""
        status, body = api.get("/api/set-browse/")

        assert status == 400, body
        assert "cache" not in body["error"].lower()
        assert "set code" in body["error"].lower()
