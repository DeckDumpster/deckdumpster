"""
Tests for Decks, Binders, and Collection Views.

Tests the repository layer for:
  1. CRUD operations on decks, binders, and collection views
  2. Card assignment to decks/binders
  3. Mutual exclusivity constraint
  4. Move cards between containers
  5. Delete cascade (unassigns cards, doesn't delete them)
  6. Migration v25 -> v26

To run: uv run pytest tests/test_decks_binders.py -v
"""

import sqlite3
import tempfile
import os

import pytest

from mtg_collector.db.schema import init_db, get_current_version
from mtg_collector.db.models import (
    Binder,
    BinderRepository,
    Card,
    CardRepository,
    CollectionEntry,
    CollectionRepository,
    CollectionView,
    CollectionViewRepository,
    Deck,
    DeckRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)


@pytest.fixture
def db():
    """Create a fresh in-memory database with schema applied."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    yield conn

    conn.close()
    os.unlink(db_path)


@pytest.fixture
def seeded_db(db):
    """Database with some test cards in the collection."""
    set_repo = SetRepository(db)
    card_repo = CardRepository(db)
    printing_repo = PrintingRepository(db)
    collection_repo = CollectionRepository(db)

    set_repo.upsert(Set(set_code="test", set_name="Test Set"))
    card_repo.upsert(Card(oracle_id="oracle-1", name="Lightning Bolt"))
    card_repo.upsert(Card(oracle_id="oracle-2", name="Counterspell"))
    card_repo.upsert(Card(oracle_id="oracle-3", name="Giant Growth"))
    printing_repo.upsert(Printing(printing_id="p1", oracle_id="oracle-1", set_code="test", collector_number="1"))
    printing_repo.upsert(Printing(printing_id="p2", oracle_id="oracle-2", set_code="test", collector_number="2"))
    printing_repo.upsert(Printing(printing_id="p3", oracle_id="oracle-3", set_code="test", collector_number="3"))

    ids = []
    for pid in ["p1", "p2", "p3"]:
        entry = CollectionEntry(id=None, printing_id=pid, finish="nonfoil")
        new_id = collection_repo.add(entry)
        ids.append(new_id)
    db.commit()

    return db, ids


# =============================================================================
# Schema/Migration
# =============================================================================

class TestMigration:
    def test_fresh_install_has_v27(self, db):
        assert get_current_version(db) == 27

    def test_tables_exist(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "decks" in tables
        assert "binders" in tables
        assert "collection_views" in tables

    def test_collection_has_new_columns(self, db):
        cols = [r[1] for r in db.execute("PRAGMA table_info(collection)").fetchall()]
        assert "deck_id" in cols
        assert "binder_id" in cols
        assert "deck_zone" in cols


# =============================================================================
# DeckRepository
# =============================================================================

class TestDeckRepository:
    def test_create_and_get(self, db):
        repo = DeckRepository(db)
        deck = Deck(id=None, name="Test Deck", format="commander")
        deck_id = repo.add(deck)
        db.commit()

        result = repo.get(deck_id)
        assert result is not None
        assert result["name"] == "Test Deck"
        assert result["format"] == "commander"
        assert result["card_count"] == 0

    def test_list_all(self, db):
        repo = DeckRepository(db)
        repo.add(Deck(id=None, name="Deck A"))
        repo.add(Deck(id=None, name="Deck B"))
        db.commit()

        decks = repo.list_all()
        assert len(decks) == 2
        names = {d["name"] for d in decks}
        assert names == {"Deck A", "Deck B"}

    def test_update(self, db):
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Old Name"))
        db.commit()

        repo.update(deck_id, {"name": "New Name", "format": "modern"})
        db.commit()

        result = repo.get(deck_id)
        assert result["name"] == "New Name"
        assert result["format"] == "modern"

    def test_delete_unassigns_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="To Delete"))
        deck_repo.add_cards(deck_id, card_ids[:2], zone="mainboard")
        db.commit()

        deck_repo.delete(deck_id)
        db.commit()

        # Cards should still exist but be unassigned
        collection_repo = CollectionRepository(db)
        for cid in card_ids[:2]:
            entry = collection_repo.get(cid)
            assert entry is not None
            assert entry.deck_id is None
            assert entry.deck_zone is None

    def test_add_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        db.commit()

        count = deck_repo.add_cards(deck_id, card_ids[:2], zone="mainboard")
        db.commit()

        assert count == 2
        cards = deck_repo.get_cards(deck_id)
        assert len(cards) == 2

    def test_add_cards_with_zone_filter(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        db.commit()

        deck_repo.add_cards(deck_id, [card_ids[0]], zone="mainboard")
        deck_repo.add_cards(deck_id, [card_ids[1]], zone="sideboard")
        db.commit()

        mainboard = deck_repo.get_cards(deck_id, zone="mainboard")
        sideboard = deck_repo.get_cards(deck_id, zone="sideboard")
        assert len(mainboard) == 1
        assert len(sideboard) == 1

    def test_remove_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        deck_repo.add_cards(deck_id, card_ids, zone="mainboard")
        db.commit()

        count = deck_repo.remove_cards(deck_id, card_ids[:1])
        db.commit()

        assert count == 1
        cards = deck_repo.get_cards(deck_id)
        assert len(cards) == 2

    def test_move_cards_from_binder_to_deck(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)

        binder_id = binder_repo.add(Binder(id=None, name="My Binder"))
        binder_repo.add_cards(binder_id, [card_ids[0]])
        db.commit()

        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        count = deck_repo.move_cards([card_ids[0]], deck_id, zone="mainboard")
        db.commit()

        assert count == 1
        # Should be in the deck now, not the binder
        deck_cards = deck_repo.get_cards(deck_id)
        binder_cards = binder_repo.get_cards(binder_id)
        assert len(deck_cards) == 1
        assert len(binder_cards) == 0


# =============================================================================
# BinderRepository
# =============================================================================

class TestBinderRepository:
    def test_create_and_get(self, db):
        repo = BinderRepository(db)
        binder_id = repo.add(Binder(id=None, name="Trade Binder", color="blue"))
        db.commit()

        result = repo.get(binder_id)
        assert result is not None
        assert result["name"] == "Trade Binder"
        assert result["color"] == "blue"
        assert result["card_count"] == 0

    def test_add_cards(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="My Binder"))
        db.commit()

        count = binder_repo.add_cards(binder_id, card_ids)
        db.commit()

        assert count == 3
        cards = binder_repo.get_cards(binder_id)
        assert len(cards) == 3

    def test_delete_unassigns_cards(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="To Delete"))
        binder_repo.add_cards(binder_id, card_ids)
        db.commit()

        binder_repo.delete(binder_id)
        db.commit()

        collection_repo = CollectionRepository(db)
        for cid in card_ids:
            entry = collection_repo.get(cid)
            assert entry is not None
            assert entry.binder_id is None


# =============================================================================
# Exclusivity Constraint
# =============================================================================

class TestExclusivity:
    def test_cannot_add_to_deck_if_in_binder(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)

        binder_id = binder_repo.add(Binder(id=None, name="Binder"))
        binder_repo.add_cards(binder_id, [card_ids[0]])
        db.commit()

        deck_id = deck_repo.add(Deck(id=None, name="Deck"))
        db.commit()

        with pytest.raises(ValueError, match="already assigned"):
            deck_repo.add_cards(deck_id, [card_ids[0]])

    def test_cannot_add_to_binder_if_in_deck(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)

        deck_id = deck_repo.add(Deck(id=None, name="Deck"))
        deck_repo.add_cards(deck_id, [card_ids[0]], zone="mainboard")
        db.commit()

        binder_id = binder_repo.add(Binder(id=None, name="Binder"))
        db.commit()

        with pytest.raises(ValueError, match="already assigned"):
            binder_repo.add_cards(binder_id, [card_ids[0]])

    def test_move_bypasses_exclusivity(self, seeded_db):
        """Move should atomically reassign, not fail on exclusivity."""
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)

        deck_id = deck_repo.add(Deck(id=None, name="Deck"))
        deck_repo.add_cards(deck_id, [card_ids[0]], zone="mainboard")
        db.commit()

        binder_id = binder_repo.add(Binder(id=None, name="Binder"))
        db.commit()

        # Move from deck to binder should work
        count = binder_repo.move_cards([card_ids[0]], binder_id)
        db.commit()
        assert count == 1

        entry = CollectionRepository(db).get(card_ids[0])
        assert entry.binder_id == binder_id
        assert entry.deck_id is None
        assert entry.deck_zone is None


# =============================================================================
# CollectionViewRepository
# =============================================================================

class TestCollectionViewRepository:
    def test_create_and_get(self, db):
        repo = CollectionViewRepository(db)
        view = CollectionView(id=None, name="My View", filters_json='{"color": "R"}')
        view_id = repo.add(view)
        db.commit()

        result = repo.get(view_id)
        assert result is not None
        assert result["name"] == "My View"
        assert result["filters_json"] == '{"color": "R"}'

    def test_list_all(self, db):
        repo = CollectionViewRepository(db)
        repo.add(CollectionView(id=None, name="View A", filters_json="{}"))
        repo.add(CollectionView(id=None, name="View B", filters_json="{}"))
        db.commit()

        views = repo.list_all()
        assert len(views) == 2

    def test_update(self, db):
        repo = CollectionViewRepository(db)
        view_id = repo.add(CollectionView(id=None, name="Old", filters_json="{}"))
        db.commit()

        repo.update(view_id, {"name": "New", "filters_json": '{"set": "MKM"}'})
        db.commit()

        result = repo.get(view_id)
        assert result["name"] == "New"
        assert result["filters_json"] == '{"set": "MKM"}'

    def test_delete(self, db):
        repo = CollectionViewRepository(db)
        view_id = repo.add(CollectionView(id=None, name="To Delete", filters_json="{}"))
        db.commit()

        assert repo.delete(view_id)
        db.commit()
        assert repo.get(view_id) is None


# =============================================================================
# CollectionEntry new fields
# =============================================================================

class TestCollectionEntryFields:
    def test_entry_has_deck_binder_fields(self, seeded_db):
        db, card_ids = seeded_db
        collection_repo = CollectionRepository(db)
        entry = collection_repo.get(card_ids[0])
        assert entry.deck_id is None
        assert entry.binder_id is None
        assert entry.deck_zone is None

    def test_entry_reflects_deck_assignment(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        deck_repo.add_cards(deck_id, [card_ids[0]], zone="commander")
        db.commit()

        entry = CollectionRepository(db).get(card_ids[0])
        assert entry.deck_id == deck_id
        assert entry.deck_zone == "commander"
        assert entry.binder_id is None
