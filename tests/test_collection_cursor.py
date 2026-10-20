"""Keyset cursors on /api/collection.

A window used to be LIMIT/OFFSET, so a deep one re-ran the query and discarded
every earlier row. The cursor names the last row seen and the next window seeks
past it. What has to hold is that walking by cursor is the same walk as the
one-shot listing: every row once, in the same order, ties included, for every
sort and both directions on every template.

To run: uv run pytest tests/test_collection_cursor.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db import page_cursor
from mtg_collector.db.schema import init_db, refresh_latest_prices
from tests.test_collection_totals import _call

NOW = "2025-01-01T00:00:00.000Z"
SORTS = ["name", "cmc", "rarity", "set", "color", "qty", "collector_number",
         "date_added", "price", "tcg_price", "ck_price", ""]


@pytest.fixture
def tied_db():
    """Names, cmc, rarity, set and price all collide on purpose, and prices and
    order ids are NULL for some rows, so every tie-break and NULL branch runs."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    rarities = ["common", "uncommon", "rare", "mythic"]
    for s in ("aaa", "bbb"):
        conn.execute("INSERT INTO sets (set_code, set_name) VALUES (?, ?)", (s, s))
    n = 0
    for set_code in ("aaa", "bbb"):
        for i in range(1, 9):
            n += 1
            name = f"Card {i % 4}"  # four names, each on four printings
            conn.execute(
                "INSERT INTO cards (oracle_id, name, cmc, color_identity) VALUES (?, ?, ?, ?)",
                (f"o{n}", name, i % 3, '["R"]' if i % 2 else '["U"]'),
            )
            conn.execute(
                "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, "
                "rarity, finishes, card_name) VALUES (?, ?, ?, ?, ?, '[\"nonfoil\",\"foil\"]', ?)",
                (f"p{n}", f"o{n}", set_code, str(i), rarities[i % 4], name),
            )
            if i % 5:
                conn.execute(
                    "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
                    "VALUES (?, ?, 'tcgplayer', 'normal', ?, '2025-01-01')",
                    (set_code, str(i), float(i % 3)),  # ties across both sets
                )
            if i % 4:
                for copy in range(i % 3 + 1):
                    conn.execute(
                        "INSERT INTO collection (printing_id, finish, acquired_at, source, status, card_name) "
                        "VALUES (?, ?, ?, 'manual', 'owned', ?)",
                        (f"p{n}", "foil" if copy == 2 else "nonfoil",
                         f"2025-01-0{(copy + i) % 3 + 1}T00:00:00.000Z", name),
                    )
    refresh_latest_prices(conn)
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _walk(db, limit, **query):
    rows, cursor, calls = [], None, 0
    while True:
        params = {**query, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        body = _call(db, params)
        rows.extend(body["rows"])
        cursor = body["next_cursor"]
        calls += 1
        assert calls < 200
        if not cursor:
            return rows, body


def _ident(row):
    return (row["printing_id"], row.get("collection_id"), row["finish"], row["condition"],
            row["status"], row.get("order_id"))


TEMPLATES = {"owned": {}, "copies": {"expand": "copies"}, "unowned": {"q": "is:unowned"}}


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("template", TEMPLATES)
def test_cursor_walk_is_the_one_shot_listing(tied_db, template, sort, order):
    query = {**TEMPLATES[template], "sort": sort, "order": order}
    whole = _call(tied_db, {**query, "limit": 1000})["rows"]
    assert len(whole) > 7
    for limit in (1, 3, 5):
        walked, _ = _walk(tied_db, limit, **query)
        assert [_ident(r) for r in walked] == [_ident(r) for r in whole]
        assert len({_ident(r) for r in walked}) == len(walked)


def test_walk_carries_total_and_needs_no_known_total(tied_db):
    first = _call(tied_db, {"limit": 3})
    second = _call(tied_db, {"limit": 3, "cursor": first["next_cursor"]})
    assert second["total"] == first["total"]


def test_walk_ends_with_no_cursor(tied_db):
    _, last = _walk(tied_db, 4)
    assert last["next_cursor"] is None


def test_cursor_for_another_query_is_refused(tied_db):
    cur = _call(tied_db, {"limit": 3, "sort": "name"})["next_cursor"]
    with pytest.raises(AssertionError) as e:
        _call(tied_db, {"limit": 3, "sort": "cmc", "cursor": cur})
    assert "different query or sort" in str(e.value)
    with pytest.raises(AssertionError) as e:
        _call(tied_db, {"limit": 3, "sort": "name", "order": "desc", "cursor": cur})
    assert "different query or sort" in str(e.value)
    with pytest.raises(AssertionError) as e:
        _call(tied_db, {"limit": 3, "sort": "name", "q": "r:rare", "cursor": cur})
    assert "different query or sort" in str(e.value)


def test_garbage_cursor_and_cursor_with_offset_are_refused(tied_db):
    with pytest.raises(AssertionError):
        _call(tied_db, {"cursor": "not-a-cursor"})
    cur = _call(tied_db, {"limit": 3})["next_cursor"]
    with pytest.raises(AssertionError) as e:
        _call(tied_db, {"cursor": cur, "offset": 3})
    assert "exclusive" in str(e.value)


def test_offset_still_works_and_agrees(tied_db):
    whole = _call(tied_db, {"limit": 1000})["rows"]
    page = _call(tied_db, {"limit": 3, "offset": 3, "known_total": len(whole)})
    assert [_ident(r) for r in page["rows"]] == [_ident(r) for r in whole[3:6]]


def test_seek_handles_null_keys():
    asc, p = page_cursor.seek(["a", "b"], [None, 2], desc=False)
    assert "a IS NOT NULL" in asc and "a IS ?" in asc and p == [None, 2]
    desc, p = page_cursor.seek(["a"], [None], desc=True)
    assert desc == "0" and p == []
