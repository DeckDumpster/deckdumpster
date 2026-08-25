"""`mtg cache set` must fill the same set-level columns the bulk path does.

The per-set path used to upsert set metadata only when no `sets` row existed.
`mtg data import` and the TCGCSV sealed importer create stub rows carrying just
(set_code, set_name), so on any set they reached first the guard held and
released_at / set_type / digital / total_set_size stayed NULL forever -- which
is how prod ended up with hob.released_at NULL and hoc.released_at populated
after both were cached the same way by hand.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.cli import cache_cmd
from mtg_collector.db import get_connection, init_db
from mtg_collector.db.connection import close_connection
from mtg_collector.services.bulk_import import ScryfallBulkClient

SET_DATA = {
    "code": "hob",
    "name": "Heroes of Borderlands",
    "set_type": "expansion",
    "released_at": "2026-08-14",
    "digital": False,
    "card_count": 2,
}

CARD_DATA = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "oracle_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "name": "Claptrap, Stairs Nemesis",
        "set": "hob",
        "collector_number": "1",
        "rarity": "rare",
        "type_line": "Legendary Creature — Robot",
        "oracle_text": "Minion detected.",
        "mana_cost": "{2}{R}",
        "cmc": 3.0,
        "colors": ["R"],
        "color_identity": ["R"],
        "finishes": ["nonfoil", "foil"],
        "image_uris": {"normal": "https://example.invalid/1.jpg"},
    },
]


class _FakeScryfall:
    """Stands in for ScryfallAPI — the cache commands are the only network path."""

    def __init__(self):
        self.get_set_calls = 0

    def get_set(self, set_code):
        self.get_set_calls += 1
        return dict(SET_DATA) if set_code.lower() == "hob" else None

    def get_set_cards(self, set_code):
        return [dict(c) for c in CARD_DATA] if set_code.lower() == "hob" else []

    # Conversions are the real ones; only the transport is faked.
    to_set_model = ScryfallBulkClient.to_set_model
    to_card_model = ScryfallBulkClient.to_card_model
    to_printing_model = ScryfallBulkClient.to_printing_model


@pytest.fixture
def db_path(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    # get_connection caches one connection per path at module scope, and
    # cache_set() reaches for the same one -- so hand it back rather than
    # closing it out from under the code under test.
    close_connection()
    init_db(get_connection(tmp.name))

    fake = _FakeScryfall()
    monkeypatch.setattr(cache_cmd, "ScryfallAPI", lambda: fake)
    # get_shared_write_path resolves to a deployed instance's shared DB; here the
    # temp file is the whole database.
    monkeypatch.setattr(cache_cmd, "get_shared_write_path", lambda p: p)
    yield tmp.name
    close_connection()
    Path(tmp.name).unlink(missing_ok=True)


def _set_row(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM sets WHERE set_code = 'hob'").fetchone()
    conn.close()
    return row


def test_cache_set_fills_metadata_on_a_fresh_set(db_path):
    cache_cmd.cache_set(db_path=db_path, set_code="HOB")

    row = _set_row(db_path)
    assert row["released_at"] == "2026-08-14"
    assert row["set_type"] == "expansion"
    assert row["total_set_size"] == 2
    assert row["cards_fetched_at"] is not None


def test_cache_set_fills_metadata_over_an_existing_stub(db_path):
    """The regression: a stub row from `mtg data import` used to block the upsert."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO sets (set_code, set_name) VALUES ('hob', 'Heroes of Borderlands')"
    )
    conn.commit()
    conn.close()

    cache_cmd.cache_set(db_path=db_path, set_code="HOB")

    row = _set_row(db_path)
    assert row["released_at"] == "2026-08-14"
    assert row["set_type"] == "expansion"
    assert row["digital"] == 0
    assert row["total_set_size"] == 2


def test_cache_set_keeps_base_set_size_written_by_mtgjson(db_path):
    """Scryfall knows nothing about base_set_size; the refresh must not blank it."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO sets (set_code, set_name) VALUES ('hob', 'Heroes of Borderlands')"
    )
    conn.execute("UPDATE sets SET base_set_size = 271 WHERE set_code = 'hob'")
    conn.commit()
    conn.close()

    cache_cmd.cache_set(db_path=db_path, set_code="HOB")

    assert _set_row(db_path)["base_set_size"] == 271


def test_cache_set_indexes_new_cards_for_full_text_search(db_path):
    """cards_fts is external-content with no triggers, so upsert alone leaves it stale."""
    cache_cmd.cache_set(db_path=db_path, set_code="HOB")

    conn = sqlite3.connect(db_path)
    hits = conn.execute(
        "SELECT COUNT(*) FROM cards_fts WHERE cards_fts MATCH 'detected'"
    ).fetchone()[0]
    conn.close()
    assert hits == 1
