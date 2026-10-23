"""Deck groups: a named container a cube's packs are managed through.

Driven through the handler's own route (`_deck_groups_route`), the way the
server dispatches /api/deck-groups, so CRUDL, release-all and both delete modes
are the real API's answers and not a repository's.

To run: uv run pytest tests/test_deck_groups.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import (
    CollectionEntry,
    CollectionRepository,
    Deck,
    DeckRepository,
)
from mtg_collector.db.schema import SCHEMA_VERSION, get_current_version, init_db
from tests.legacy_handler import bare_handler

NOW = "2025-01-01T00:00:00.000Z"


@pytest.fixture
def db_path():
    path = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at)"
        " VALUES ('tst', 'Test Set', '2025-01-01', ?)", (NOW,))
    conn.execute("INSERT INTO cards (oracle_id, name, type_line) VALUES ('o1', 'Card 1', 'Creature')")
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity, finishes)"
        " VALUES ('p1', 'o1', 'tst', '1', 'R', '[\"nonfoil\"]')")
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def call(db_path, method, path, body=None):
    handler = bare_handler()
    handler.db_path = db_path
    out = []
    handler._send_json = lambda obj, status=200: out.append((status, obj))
    handler._read_json_body = lambda: body
    handler._deck_groups_route(method, path, {})
    return out[-1]


def call_q(db_path, method, path, params):
    handler = bare_handler()
    handler.db_path = db_path
    out = []
    handler._send_json = lambda obj, status=200: out.append((status, obj))
    handler._deck_groups_route(method, path, params)
    return out[-1]


def conn_of(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def make_deck(db_path, name, group=None, with_copy=True):
    """A constructed deck holding one real copy; returns (deck_id, copy_id)."""
    conn = conn_of(db_path)
    deck_id = DeckRepository(conn).add(Deck(id=None, name=name, state_id=3, deck_group=group))
    copy_id = None
    if with_copy:
        copy_id = CollectionRepository(conn).add(CollectionEntry(
            id=None, printing_id="p1", finish="nonfoil", condition="Near Mint",
            language="en", status="owned", source="test"))
        conn.execute(
            "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity)"
            " VALUES (?, 'p1', ?, 'mainboard', 1)", (deck_id, copy_id))
    conn.commit()
    conn.close()
    return deck_id, copy_id


def test_schema_is_current(db_path):
    conn = conn_of(db_path)
    assert get_current_version(conn) == SCHEMA_VERSION
    assert "deck_group" in [r[1] for r in conn.execute("PRAGMA table_info(decks)")]


def test_crudl(db_path):
    status, g = call(db_path, "POST", "/api/deck-groups",
                     {"name": "Cube", "description": "d", "format": "Jumpstart"})
    assert status == 201 and g["name"] == "Cube" and g["format"] == "Jumpstart"
    gid = g["id"]
    assert call(db_path, "GET", "/api/deck-groups")[1][0]["name"] == "Cube"
    status, got = call(db_path, "GET", f"/api/deck-groups/{gid}")
    assert status == 200 and got["decks"] == [] and got["description"] == "d"
    status, upd = call(db_path, "PUT", f"/api/deck-groups/{gid}", {"description": "e"})
    assert status == 200 and upd["description"] == "e" and upd["name"] == "Cube"
    status, _ = call_q(db_path, "DELETE", f"/api/deck-groups/{gid}", {"decks": ["ungroup"]})
    assert status == 200
    assert call(db_path, "GET", f"/api/deck-groups/{gid}")[0] == 404
    assert call(db_path, "GET", "/api/deck-groups")[1] == []


def test_name_is_unique_and_required(db_path):
    call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})
    assert call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[0] == 400
    assert call(db_path, "POST", "/api/deck-groups", {"name": "  "})[0] == 400
    other = call(db_path, "POST", "/api/deck-groups", {"name": "Other"})[1]["id"]
    assert call(db_path, "PUT", f"/api/deck-groups/{other}", {"name": "Cube"})[0] == 400


def test_lists_sort_naturally(db_path):
    for n in ("Pack 10", "Pack 2", "Pack 1"):
        call(db_path, "POST", "/api/deck-groups", {"name": n})
    assert [g["name"] for g in call(db_path, "GET", "/api/deck-groups")[1]] == [
        "Pack 1", "Pack 2", "Pack 10"]


def test_membership_and_rename_follow_the_group(db_path):
    gid = call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[1]["id"]
    a, _ = make_deck(db_path, "Pack 2", group="Cube", with_copy=False)
    b, _ = make_deck(db_path, "Pack 10", group="Cube", with_copy=False)
    got = call(db_path, "GET", f"/api/deck-groups/{gid}")[1]
    assert [d["id"] for d in got["decks"]] == [a, b] and got["deck_count"] == 2
    call(db_path, "PUT", f"/api/deck-groups/{gid}", {"name": "Cube 2"})
    conn = conn_of(db_path)
    assert DeckRepository(conn).get(a)["deck_group"] == "Cube 2"
    assert DeckRepository(conn).get(a)["deck_group_id"] == gid


def test_a_deck_cannot_join_a_group_that_does_not_exist(db_path):
    conn = conn_of(db_path)
    deck_id = DeckRepository(conn).add(Deck(id=None, name="D"))
    with pytest.raises(ValueError):
        DeckRepository(conn).update(deck_id, {"deck_group": "Nope"})


def test_release_all_returns_every_copy_and_keeps_the_decks(db_path):
    gid = call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[1]["id"]
    a, ca = make_deck(db_path, "Pack 1", group="Cube")
    b, cb = make_deck(db_path, "Pack 2", group="Cube")
    outside, co = make_deck(db_path, "Elsewhere")
    status, out = call(db_path, "POST", f"/api/deck-groups/{gid}/release", {})
    assert status == 200 and out["released"] == 2
    conn = conn_of(db_path)
    held = {r[0] for r in conn.execute("SELECT collection_id FROM deck_cards")}
    assert held == {co}
    decks = DeckRepository(conn)
    assert decks.get(a)["state"] == "ready" and decks.get(a)["deck_group"] == "Cube"
    assert decks.get(outside)["state"] == "constructed"
    assert conn.execute("SELECT COUNT(*) FROM collection WHERE id IN (?, ?)", (ca, cb)).fetchone()[0] == 2


def test_delete_ungroup_keeps_the_decks(db_path):
    gid = call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[1]["id"]
    a, _ = make_deck(db_path, "Pack 1", group="Cube")
    status, out = call_q(db_path, "DELETE", f"/api/deck-groups/{gid}", {"decks": ["ungroup"]})
    assert (status, out) == (200, {"decks": 1, "decks_deleted": 0})
    deck = DeckRepository(conn_of(db_path)).get(a)
    assert deck["deck_group"] is None


def test_delete_with_decks_removes_them_and_frees_their_cards(db_path):
    gid = call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[1]["id"]
    a, ca = make_deck(db_path, "Pack 1", group="Cube")
    outside, _ = make_deck(db_path, "Elsewhere")
    status, out = call_q(db_path, "DELETE", f"/api/deck-groups/{gid}", {"decks": ["delete_decks"]})
    assert (status, out) == (200, {"decks": 1, "decks_deleted": 1})
    conn = conn_of(db_path)
    assert DeckRepository(conn).get(a) is None
    assert DeckRepository(conn).get(outside) is not None
    assert conn.execute("SELECT COUNT(*) FROM collection WHERE id = ?", (ca,)).fetchone()[0] == 1


def test_delete_must_choose_a_mode(db_path):
    gid = call(db_path, "POST", "/api/deck-groups", {"name": "Cube"})[1]["id"]
    assert call_q(db_path, "DELETE", f"/api/deck-groups/{gid}", {})[0] == 400
    assert call_q(db_path, "DELETE", f"/api/deck-groups/{gid}", {"decks": ["x"]})[0] == 400
    assert call(db_path, "GET", f"/api/deck-groups/{gid}")[0] == 200


def test_migration_from_v54_adds_groups(db_path):
    conn = conn_of(db_path)
    conn.execute("DROP TABLE deck_groups")
    conn.execute("DROP INDEX idx_decks_group")
    conn.execute("ALTER TABLE decks DROP COLUMN deck_group")
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (54, ?)", (NOW,))
    conn.commit()
    init_db(conn)
    assert get_current_version(conn) == SCHEMA_VERSION
    conn.execute("INSERT INTO deck_groups (name, created_at, updated_at) VALUES ('g', ?, ?)", (NOW, NOW))
    assert "deck_group" in [r[1] for r in conn.execute("PRAGMA table_info(decks)")]
