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

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import (
    Binder,
    BinderRepository,
    Card,
    CardRepository,
    CollectionEntry,
    CollectionRepository,
    CollectionView,
    CollectionViewRepository,
    DECK_STATE_CONSTRUCTED,
    DECK_STATE_IDEA,
    Deck,
    DeckRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import get_current_version, init_db


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
    def test_fresh_install_has_v41(self, db):
        assert get_current_version(db) == 41

    def test_tables_exist(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "decks" in tables
        assert "binders" in tables
        assert "collection_views" in tables

    def test_collection_and_deck_cards_schema(self, db):
        cols = [r[1] for r in db.execute("PRAGMA table_info(collection)").fetchall()]
        assert "binder_id" in cols
        assert "deck_id" not in cols
        assert "deck_zone" not in cols
        # deck_cards join table exists
        dc_cols = [r[1] for r in db.execute("PRAGMA table_info(deck_cards)").fetchall()]
        assert "deck_id" in dc_cols
        assert "printing_id" in dc_cols
        assert "collection_id" in dc_cols
        assert "zone" in dc_cols
        assert "quantity" in dc_cols

    def test_deck_states_table_seeded(self, db):
        rows = db.execute("SELECT id, name FROM deck_states ORDER BY id").fetchall()
        states = {r["id"]: r["name"] for r in rows}
        assert states == {1: "idea", 2: "ready", 3: "constructed"}

    def test_decks_has_state_id_not_hypothetical(self, db):
        cols = [r[1] for r in db.execute("PRAGMA table_info(decks)").fetchall()]
        assert "state_id" in cols
        assert "hypothetical" not in cols
        assert "deck_status" not in cols


class TestMigrationV39ToV40:
    """Test upgrading a v39 DB with hypothetical + deck_status to v40 with deck_states."""

    def _make_v39_db(self):
        """Create a minimal v39 DB with both hypothetical and non-hypothetical decks."""
        f = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        db_path = f.name
        f.close()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            INSERT INTO schema_version (version, applied_at) VALUES (39, '2025-01-01');

            CREATE TABLE cards (oracle_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                type_line TEXT, mana_cost TEXT, cmc REAL DEFAULT 0,
                colors TEXT DEFAULT '[]', color_identity TEXT DEFAULT '[]');
            CREATE TABLE sets (set_code TEXT PRIMARY KEY, set_name TEXT NOT NULL);
            CREATE TABLE printings (
                printing_id TEXT PRIMARY KEY,
                oracle_id TEXT NOT NULL REFERENCES cards(oracle_id),
                set_code TEXT NOT NULL REFERENCES sets(set_code),
                collector_number TEXT, rarity TEXT, promo INTEGER DEFAULT 0, artist TEXT,
                image_uri TEXT, frame_effects TEXT, border_color TEXT, full_art INTEGER DEFAULT 0,
                promo_types TEXT, finishes TEXT, raw_json TEXT
            );
            CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_number TEXT,
                source TEXT, seller_name TEXT, order_date TEXT, subtotal REAL, shipping REAL,
                tax REAL, total REAL, shipping_status TEXT, estimated_delivery TEXT,
                notes TEXT, created_at TEXT NOT NULL);
            CREATE TABLE binders (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                color TEXT, type TEXT, storage_location TEXT, notes TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE batches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                source TEXT, deck_id INTEGER, created_at TEXT NOT NULL);
            CREATE TABLE collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                printing_id TEXT NOT NULL REFERENCES printings(printing_id),
                finish TEXT NOT NULL DEFAULT 'nonfoil',
                condition TEXT NOT NULL DEFAULT 'Near Mint',
                language TEXT NOT NULL DEFAULT 'English',
                purchase_price REAL, acquired_at TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual', source_image TEXT,
                notes TEXT, tags TEXT, tradelist INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'owned', sale_price REAL,
                order_id INTEGER REFERENCES orders(id),
                binder_id INTEGER REFERENCES binders(id),
                batch_id INTEGER REFERENCES batches(id)
            );
            CREATE TABLE decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, description TEXT, format TEXT,
                is_precon INTEGER NOT NULL DEFAULT 0,
                sleeve_color TEXT, deck_box TEXT, storage_location TEXT,
                origin_set_code TEXT, origin_theme TEXT, origin_variation INTEGER,
                hypothetical INTEGER NOT NULL DEFAULT 0,
                deck_status TEXT NOT NULL DEFAULT 'under_construction'
                    CHECK(deck_status IN ('under_construction', 'ready', 'constructed')),
                commander_oracle_id TEXT, commander_printing_id TEXT,
                plan TEXT, sub_plans TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE deck_expected_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
                printing_id TEXT NOT NULL REFERENCES printings(printing_id),
                zone TEXT NOT NULL DEFAULT 'mainboard',
                quantity INTEGER NOT NULL DEFAULT 1,
                UNIQUE(deck_id, printing_id, zone)
            );
            CREATE TABLE deck_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
                printing_id TEXT NOT NULL REFERENCES printings(printing_id),
                collection_id INTEGER REFERENCES collection(id) ON DELETE SET NULL,
                zone TEXT NOT NULL DEFAULT 'mainboard'
                    CHECK(zone IN ('mainboard', 'sideboard', 'commander')),
                quantity INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
            CREATE TABLE movement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER, from_deck_id INTEGER, to_deck_id INTEGER,
                from_binder_id INTEGER, to_binder_id INTEGER,
                from_zone TEXT, to_zone TEXT, note TEXT,
                moved_at TEXT NOT NULL
            );
            CREATE TABLE status_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER, old_status TEXT, new_status TEXT,
                changed_at TEXT NOT NULL
            );

            -- Test data
            INSERT INTO sets VALUES ('test', 'Test Set');
            INSERT INTO cards (oracle_id, name) VALUES ('o1', 'Lightning Bolt');
            INSERT INTO cards (oracle_id, name) VALUES ('o2', 'Counterspell');
            INSERT INTO printings (printing_id, oracle_id, set_code, collector_number)
                VALUES ('p1', 'o1', 'test', '1');
            INSERT INTO printings (printing_id, oracle_id, set_code, collector_number)
                VALUES ('p2', 'o2', 'test', '2');
            INSERT INTO collection (printing_id, finish, acquired_at, source)
                VALUES ('p1', 'nonfoil', '2025-01-01', 'manual');
            INSERT INTO collection (printing_id, finish, acquired_at, source)
                VALUES ('p2', 'nonfoil', '2025-01-01', 'manual');

            -- Hypothetical deck with expected cards + orphan deck_cards
            INSERT INTO decks (name, format, hypothetical, deck_status, created_at, updated_at)
                VALUES ('My Ideas', 'commander', 1, 'under_construction', '2025-01-01', '2025-01-01');
            INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity)
                VALUES (1, 'p1', 'mainboard', 1);
            INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity)
                VALUES (1, 'p1', NULL, 'mainboard', 1);

            -- Physical constructed deck with real card assignment
            INSERT INTO decks (name, format, hypothetical, deck_status, created_at, updated_at)
                VALUES ('Built Deck', 'commander', 0, 'constructed', '2025-01-01', '2025-01-01');
            INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity)
                VALUES (2, 'p2', 2, 'mainboard', 1);

            -- Physical under_construction deck
            INSERT INTO decks (name, format, hypothetical, deck_status, created_at, updated_at)
                VALUES ('WIP Deck', 'standard', 0, 'under_construction', '2025-01-01', '2025-01-01');

            -- Create collection_view (matches v39 schema)
            CREATE VIEW collection_view AS
            SELECT c.id, card.name, s.set_name, p.set_code, p.collector_number,
                   p.rarity, p.promo, c.finish, c.condition, c.language,
                   card.name AS type_line, '' AS mana_cost, 0 AS cmc,
                   '[]' AS colors, '[]' AS color_identity, p.artist,
                   c.purchase_price, c.acquired_at, c.source, c.source_image,
                   c.notes, c.tags, c.tradelist, c.status, c.sale_price,
                   c.printing_id, p.oracle_id, c.order_id,
                   dc.deck_id, dc.zone AS deck_zone, c.binder_id, c.batch_id,
                   d.name AS deck_name, b.name AS binder_name, bat.name AS batch_name
            FROM collection c
            JOIN printings p ON c.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            LEFT JOIN deck_cards dc ON dc.collection_id = c.id
            LEFT JOIN decks d ON dc.deck_id = d.id
            LEFT JOIN binders b ON c.binder_id = b.id
            LEFT JOIN batches bat ON c.batch_id = bat.id;
        """)
        conn.commit()
        return conn, db_path

    def test_hypothetical_becomes_idea(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            row = conn.execute("SELECT state_id FROM decks WHERE name = 'My Ideas'").fetchone()
            assert row["state_id"] == DECK_STATE_IDEA
        finally:
            conn.close()
            os.unlink(db_path)

    def test_constructed_stays_constructed(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            row = conn.execute("SELECT state_id FROM decks WHERE name = 'Built Deck'").fetchone()
            assert row["state_id"] == DECK_STATE_CONSTRUCTED
        finally:
            conn.close()
            os.unlink(db_path)

    def test_under_construction_becomes_ready(self):
        conn, db_path = self._make_v39_db()
        try:
            from mtg_collector.db.models import DECK_STATE_READY
            init_db(conn)
            row = conn.execute("SELECT state_id FROM decks WHERE name = 'WIP Deck'").fetchone()
            assert row["state_id"] == DECK_STATE_READY
        finally:
            conn.close()
            os.unlink(db_path)

    def test_orphan_deck_cards_cleaned_up(self):
        conn, db_path = self._make_v39_db()
        try:
            # Before migration: idea deck has a NULL-collection_id deck_cards row
            orphans_before = conn.execute(
                "SELECT COUNT(*) as c FROM deck_cards WHERE collection_id IS NULL"
            ).fetchone()["c"]
            assert orphans_before == 1

            init_db(conn)

            # After migration: orphan rows for idea decks are gone
            orphans_after = conn.execute(
                "SELECT COUNT(*) as c FROM deck_cards WHERE collection_id IS NULL"
            ).fetchone()["c"]
            assert orphans_after == 0
        finally:
            conn.close()
            os.unlink(db_path)

    def test_hypothetical_column_removed(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(decks)").fetchall()]
            assert "hypothetical" not in cols
            assert "deck_status" not in cols
            assert "state_id" in cols
        finally:
            conn.close()
            os.unlink(db_path)

    def test_deck_states_table_exists(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            rows = conn.execute("SELECT id, name FROM deck_states ORDER BY id").fetchall()
            assert len(rows) == 3
            assert rows[0]["name"] == "idea"
            assert rows[1]["name"] == "ready"
            assert rows[2]["name"] == "constructed"
        finally:
            conn.close()
            os.unlink(db_path)

    def test_collection_view_includes_deck_state(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            # The constructed deck has card_id=2 assigned
            row = conn.execute(
                "SELECT deck_state FROM collection_view WHERE deck_id = 2"
            ).fetchone()
            assert row["deck_state"] == "constructed"
        finally:
            conn.close()
            os.unlink(db_path)

    def test_physical_card_assignments_preserved(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            # Built Deck should still have its card
            row = conn.execute(
                "SELECT collection_id FROM deck_cards WHERE deck_id = 2"
            ).fetchone()
            assert row["collection_id"] == 2
        finally:
            conn.close()
            os.unlink(db_path)

    def test_expected_cards_preserved(self):
        conn, db_path = self._make_v39_db()
        try:
            init_db(conn)
            row = conn.execute(
                "SELECT printing_id FROM deck_expected_cards WHERE deck_id = 1"
            ).fetchone()
            assert row["printing_id"] == "p1"
        finally:
            conn.close()
            os.unlink(db_path)


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
        deck_id = deck_repo.add(Deck(id=None, name="To Delete", state_id=DECK_STATE_CONSTRUCTED))
        deck_repo.add_cards(deck_id, card_ids[:2], zone="mainboard")
        db.commit()

        deck_repo.delete(deck_id)
        db.commit()

        # Cards should still exist but be unassigned (no deck_cards rows)
        collection_repo = CollectionRepository(db)
        for cid in card_ids[:2]:
            entry = collection_repo.get(cid)
            assert entry is not None
            dc = db.execute(
                "SELECT * FROM deck_cards WHERE collection_id = ?", (cid,)
            ).fetchone()
            assert dc is None

    def test_add_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck", state_id=DECK_STATE_CONSTRUCTED))
        db.commit()

        count = deck_repo.add_cards(deck_id, card_ids[:2], zone="mainboard")
        db.commit()

        assert count == 2
        cards = deck_repo.get_cards(deck_id)
        assert len(cards) == 2

    def test_add_cards_with_zone_filter(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck", state_id=DECK_STATE_CONSTRUCTED))
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
        deck_id = deck_repo.add(Deck(id=None, name="My Deck", state_id=DECK_STATE_CONSTRUCTED))
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

        deck_id = deck_repo.add(Deck(id=None, name="My Deck", state_id=DECK_STATE_CONSTRUCTED))
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

        deck_id = deck_repo.add(Deck(id=None, name="Deck", state_id=DECK_STATE_CONSTRUCTED))
        db.commit()

        with pytest.raises(ValueError, match="already assigned"):
            deck_repo.add_cards(deck_id, [card_ids[0]])

    def test_cannot_add_to_binder_if_in_constructed_deck(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)

        deck_id = deck_repo.add(Deck(id=None, name="Deck", state_id=DECK_STATE_CONSTRUCTED))
        deck_repo.add_cards(deck_id, [card_ids[0]], zone="mainboard")
        db.commit()

        binder_id = binder_repo.add(Binder(id=None, name="Binder"))
        db.commit()

        with pytest.raises(ValueError, match="already assigned"):
            binder_repo.add_cards(binder_id, [card_ids[0]])

    def test_idea_deck_does_not_block_assignment(self, seeded_db):
        """Cards in idea decks should not block assignment to constructed decks."""
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)

        idea_id = deck_repo.add(Deck(id=None, name="Idea Deck", state_id=DECK_STATE_IDEA))
        deck_repo.add_cards(idea_id, [card_ids[0]], zone="mainboard")
        db.commit()

        constructed_id = deck_repo.add(Deck(id=None, name="Real Deck", state_id=DECK_STATE_CONSTRUCTED))
        db.commit()

        # Should succeed — idea decks don't block
        count = deck_repo.add_cards(constructed_id, [card_ids[0]], zone="mainboard")
        assert count == 1

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
        # No deck_cards row should exist
        dc = db.execute(
            "SELECT * FROM deck_cards WHERE collection_id = ?", (card_ids[0],)
        ).fetchone()
        assert dc is None


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
    def test_entry_has_binder_field(self, seeded_db):
        db, card_ids = seeded_db
        collection_repo = CollectionRepository(db)
        entry = collection_repo.get(card_ids[0])
        assert entry.binder_id is None

    def test_deck_assignment_via_deck_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="My Deck"))
        deck_repo.add_cards(deck_id, [card_ids[0]], zone="commander")
        db.commit()

        # Deck assignment is now in deck_cards table, not on collection
        dc = db.execute(
            "SELECT deck_id, zone FROM deck_cards WHERE collection_id = ?",
            (card_ids[0],)
        ).fetchone()
        assert dc is not None
        assert dc["deck_id"] == deck_id
        assert dc["zone"] == "commander"

        entry = CollectionRepository(db).get(card_ids[0])
        assert entry.binder_id is None


# =============================================================================
# Helpers for movement_log tests
# =============================================================================

def _get_movement_logs(db, collection_id):
    """Return all movement_log rows for a collection entry."""
    return [dict(r) for r in db.execute(
        "SELECT * FROM movement_log WHERE collection_id = ? ORDER BY id",
        (collection_id,),
    ).fetchall()]


# =============================================================================
# Schema: movement_log table
# =============================================================================

class TestMovementLogSchema:
    def test_movement_log_table_exists(self, db):
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "movement_log" in tables

    def test_movement_log_columns(self, db):
        cols = [r[1] for r in db.execute("PRAGMA table_info(movement_log)").fetchall()]
        assert "collection_id" in cols
        assert "from_deck_id" in cols
        assert "to_deck_id" in cols
        assert "from_binder_id" in cols
        assert "to_binder_id" in cols
        assert "from_zone" in cols
        assert "to_zone" in cols
        assert "changed_at" in cols
        assert "note" in cols

    def test_movement_log_index_exists(self, db):
        indexes = [r[1] for r in db.execute(
            "SELECT * FROM sqlite_master WHERE type='index'"
        ).fetchall()]
        assert "idx_movement_log_collection" in indexes


# =============================================================================
# Migration backfill
# =============================================================================

class TestMovementLogBackfill:
    def test_backfill_creates_entries_for_assigned_cards(self):
        """Verify movement_log backfill works with current schema (deck_cards join table)."""
        from mtg_collector.db.schema import SCHEMA_SQL

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = f.name
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        conn.executescript(SCHEMA_SQL)
        conn.commit()

        # Seed test data: a card assigned to a deck via deck_cards
        conn.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test')")
        conn.execute("INSERT INTO cards (oracle_id, name) VALUES ('o1', 'Bolt')")
        conn.execute("INSERT INTO printings (printing_id, oracle_id, set_code, collector_number) "
                      "VALUES ('p1', 'o1', 'tst', '1')")
        conn.execute("INSERT INTO decks (name, created_at, updated_at) VALUES ('D1', '2025-01-01', '2025-01-01')")
        conn.execute("INSERT INTO binders (name, created_at, updated_at) VALUES ('B1', '2025-01-01', '2025-01-01')")
        conn.execute("INSERT INTO collection (printing_id, finish, acquired_at, source) "
                      "VALUES ('p1', 'nonfoil', '2025-01-01', 'manual')")
        conn.execute("INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone) "
                      "VALUES (1, 'p1', 1, 'mainboard')")
        conn.execute("INSERT INTO collection (printing_id, finish, acquired_at, source, binder_id) "
                      "VALUES ('p1', 'foil', '2025-01-01', 'manual', 1)")
        conn.execute("INSERT INTO collection (printing_id, finish, acquired_at, source) "
                      "VALUES ('p1', 'nonfoil', '2025-01-01', 'manual')")
        conn.commit()

        # Verify deck assignment is in deck_cards, binder in collection
        dc = conn.execute("SELECT * FROM deck_cards WHERE collection_id = 1").fetchone()
        assert dc is not None
        assert dc["deck_id"] == 1
        assert dc["zone"] == "mainboard"

        binder_entry = conn.execute("SELECT binder_id FROM collection WHERE id = 2").fetchone()
        assert binder_entry["binder_id"] == 1

        conn.close()
        os.unlink(db_path)


# =============================================================================
# DeckRepository movement logging
# =============================================================================

class TestDeckMovementLog:
    def test_add_cards_logs_movement(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="D1"))
        deck_repo.add_cards(deck_id, card_ids[:2], zone="sideboard")
        db.commit()

        for cid in card_ids[:2]:
            logs = _get_movement_logs(db, cid)
            assert len(logs) == 1
            assert logs[0]["from_deck_id"] is None
            assert logs[0]["to_deck_id"] == deck_id
            assert logs[0]["from_zone"] is None
            assert logs[0]["to_zone"] == "sideboard"

        # Unassigned card has no logs
        assert _get_movement_logs(db, card_ids[2]) == []

    def test_remove_cards_logs_movement(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="D1"))
        deck_repo.add_cards(deck_id, card_ids[:2], zone="mainboard")
        db.commit()

        deck_repo.remove_cards(deck_id, [card_ids[0]])
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2  # add + remove
        remove_log = logs[1]
        assert remove_log["from_deck_id"] == deck_id
        assert remove_log["to_deck_id"] is None
        assert remove_log["from_zone"] == "mainboard"
        assert remove_log["to_zone"] is None

    def test_move_cards_deck_to_deck(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        d1 = deck_repo.add(Deck(id=None, name="Deck A"))
        d2 = deck_repo.add(Deck(id=None, name="Deck B"))
        deck_repo.add_cards(d1, [card_ids[0]], zone="mainboard")
        db.commit()

        deck_repo.move_cards([card_ids[0]], d2, zone="sideboard")
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2  # add to d1 + move to d2
        move_log = logs[1]
        assert move_log["from_deck_id"] == d1
        assert move_log["to_deck_id"] == d2
        assert move_log["from_zone"] == "mainboard"
        assert move_log["to_zone"] == "sideboard"

    def test_move_cards_binder_to_deck(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        deck_repo = DeckRepository(db)
        b1 = binder_repo.add(Binder(id=None, name="B1"))
        binder_repo.add_cards(b1, [card_ids[0]])
        db.commit()

        d1 = deck_repo.add(Deck(id=None, name="D1"))
        deck_repo.move_cards([card_ids[0]], d1, zone="commander")
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2  # add to binder + move to deck
        move_log = logs[1]
        assert move_log["from_binder_id"] == b1
        assert move_log["to_binder_id"] is None
        assert move_log["from_deck_id"] is None
        assert move_log["to_deck_id"] == d1
        assert move_log["to_zone"] == "commander"

    def test_delete_deck_logs_all_cards(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="To Delete"))
        deck_repo.add_cards(deck_id, card_ids, zone="mainboard")
        db.commit()

        deck_repo.delete(deck_id)
        db.commit()

        for cid in card_ids:
            logs = _get_movement_logs(db, cid)
            assert len(logs) == 2  # add + delete
            delete_log = logs[1]
            assert delete_log["from_deck_id"] == deck_id
            assert delete_log["to_deck_id"] is None
            assert delete_log["from_zone"] == "mainboard"
            assert delete_log["to_zone"] is None
            assert delete_log["note"] == "deck deleted"


# =============================================================================
# BinderRepository movement logging
# =============================================================================

class TestBinderMovementLog:
    def test_add_cards_logs_movement(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="B1"))
        binder_repo.add_cards(binder_id, card_ids[:2])
        db.commit()

        for cid in card_ids[:2]:
            logs = _get_movement_logs(db, cid)
            assert len(logs) == 1
            assert logs[0]["from_binder_id"] is None
            assert logs[0]["to_binder_id"] == binder_id
            assert logs[0]["from_deck_id"] is None
            assert logs[0]["to_deck_id"] is None

    def test_remove_cards_logs_movement(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="B1"))
        binder_repo.add_cards(binder_id, card_ids[:1])
        db.commit()

        binder_repo.remove_cards(binder_id, card_ids[:1])
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2  # add + remove
        remove_log = logs[1]
        assert remove_log["from_binder_id"] == binder_id
        assert remove_log["to_binder_id"] is None

    def test_move_cards_deck_to_binder(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)
        d1 = deck_repo.add(Deck(id=None, name="D1"))
        deck_repo.add_cards(d1, [card_ids[0]], zone="mainboard")
        db.commit()

        b1 = binder_repo.add(Binder(id=None, name="B1"))
        binder_repo.move_cards([card_ids[0]], b1)
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2
        move_log = logs[1]
        assert move_log["from_deck_id"] == d1
        assert move_log["to_deck_id"] is None
        assert move_log["from_binder_id"] is None
        assert move_log["to_binder_id"] == b1
        assert move_log["from_zone"] == "mainboard"
        assert move_log["to_zone"] is None

    def test_move_cards_binder_to_binder(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        b1 = binder_repo.add(Binder(id=None, name="B1"))
        b2 = binder_repo.add(Binder(id=None, name="B2"))
        binder_repo.add_cards(b1, [card_ids[0]])
        db.commit()

        binder_repo.move_cards([card_ids[0]], b2)
        db.commit()

        logs = _get_movement_logs(db, card_ids[0])
        assert len(logs) == 2
        move_log = logs[1]
        assert move_log["from_binder_id"] == b1
        assert move_log["to_binder_id"] == b2

    def test_delete_binder_logs_all_cards(self, seeded_db):
        db, card_ids = seeded_db
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="To Delete"))
        binder_repo.add_cards(binder_id, card_ids)
        db.commit()

        binder_repo.delete(binder_id)
        db.commit()

        for cid in card_ids:
            logs = _get_movement_logs(db, cid)
            assert len(logs) == 2  # add + delete
            delete_log = logs[1]
            assert delete_log["from_binder_id"] == binder_id
            assert delete_log["to_binder_id"] is None
            assert delete_log["note"] == "binder deleted"


# =============================================================================
# CollectionRepository.get_movement_history
# =============================================================================

class TestGetMovementHistory:
    def test_returns_empty_for_unmoved_card(self, seeded_db):
        db, card_ids = seeded_db
        repo = CollectionRepository(db)
        assert repo.get_movement_history(card_ids[0]) == []

    def test_returns_chronological_entries(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        d1 = deck_repo.add(Deck(id=None, name="D1"))
        d2 = deck_repo.add(Deck(id=None, name="D2"))
        deck_repo.add_cards(d1, [card_ids[0]], zone="mainboard")
        deck_repo.move_cards([card_ids[0]], d2, zone="sideboard")
        deck_repo.remove_cards(d2, [card_ids[0]])
        db.commit()

        repo = CollectionRepository(db)
        history = repo.get_movement_history(card_ids[0])
        assert len(history) == 3
        # Verify chronological order by id
        assert history[0]["id"] < history[1]["id"] < history[2]["id"]

    def test_joins_deck_and_binder_names(self, seeded_db):
        db, card_ids = seeded_db
        deck_repo = DeckRepository(db)
        binder_repo = BinderRepository(db)
        d1 = deck_repo.add(Deck(id=None, name="Red Deck"))
        deck_repo.add_cards(d1, [card_ids[0]], zone="mainboard")
        db.commit()

        b1 = binder_repo.add(Binder(id=None, name="Trade Binder"))
        binder_repo.move_cards([card_ids[0]], b1)
        db.commit()

        repo = CollectionRepository(db)
        history = repo.get_movement_history(card_ids[0])
        assert len(history) == 2

        # First: added to deck
        assert history[0]["to_deck_name"] == "Red Deck"
        assert history[0]["from_deck_name"] is None

        # Second: moved deck -> binder
        assert history[1]["from_deck_name"] == "Red Deck"
        assert history[1]["to_binder_name"] == "Trade Binder"
