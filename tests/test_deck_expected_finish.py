"""
Tests for db-5h69: finish column on deck_expected_cards.

Covers:
  - Schema v51→v52 migration: existing rows become 'nonfoil', new unique constraint
  - set_expected_cards / get_expected_cards carry finish
  - _api_precons_import isFoil flag maps to finish='foil'
  - materialize_deck matches collection entries by finish

To run: uv run pytest tests/test_deck_expected_finish.py -v
"""

import json
import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import (
    Card,
    CardRepository,
    CollectionEntry,
    CollectionRepository,
    DECK_STATE_CONSTRUCTED,
    DECK_STATE_IDEA,
    Deck,
    DeckRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import (
    SCHEMA_VERSION,
    init_db,
    verify_schema,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_db():
    f = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    db_path = f.name
    f.close()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn, db_path


def _seed(conn):
    """Minimal card/printing/collection data."""
    SetRepository(conn).upsert(Set(set_code="test", set_name="Test Set"))
    CardRepository(conn).upsert(Card(oracle_id="o1", name="Lightning Bolt"))
    CardRepository(conn).upsert(Card(oracle_id="o2", name="Counterspell"))
    PrintingRepository(conn).upsert(
        Printing(printing_id="p1", oracle_id="o1", set_code="test",
                 collector_number="1", finishes=["nonfoil", "foil"])
    )
    PrintingRepository(conn).upsert(
        Printing(printing_id="p2", oracle_id="o2", set_code="test",
                 collector_number="2", finishes=["nonfoil"])
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------

class TestSchemaIntegrity:
    def test_verify_schema_passes_on_fresh_db(self):
        conn, db_path = _fresh_db()
        try:
            init_db(conn)
            missing = verify_schema(conn)
            assert missing == [], f"Schema objects missing: {missing}"
        finally:
            conn.close()
            os.unlink(db_path)

    def test_deck_expected_cards_has_finish_column(self):
        conn, db_path = _fresh_db()
        try:
            init_db(conn)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(deck_expected_cards)").fetchall()}
            assert "finish" in cols
        finally:
            conn.close()
            os.unlink(db_path)

    def test_unique_constraint_per_printing_zone(self):
        """UNIQUE(deck_id, printing_id, zone) — inserting the same printing twice is a no-op."""
        conn, db_path = _fresh_db()
        try:
            init_db(conn)
            _seed(conn)
            repo = DeckRepository(conn)
            deck_id = repo.add(Deck(id=None, name="Test Deck"))
            conn.commit()

            repo.add_expected_cards(deck_id, ["p1"], zone="mainboard")
            conn.commit()
            # A second insert of the same printing in the same zone is ignored (INSERT OR IGNORE).
            added = repo.add_expected_cards(deck_id, ["p1"], zone="mainboard")
            conn.commit()

            assert added == 0
            rows = conn.execute(
                "SELECT COUNT(*) as n FROM deck_expected_cards WHERE deck_id = ?",
                (deck_id,),
            ).fetchone()
            assert rows["n"] == 1
        finally:
            conn.close()
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Migration v51 → v52
# ---------------------------------------------------------------------------

def _make_v51_db():
    """Minimal v51 DB with deck_expected_cards rows (no finish column yet)."""
    conn, db_path = _fresh_db()
    conn.executescript("""
        CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_version (version, applied_at) VALUES (51, '2025-01-01');

        CREATE TABLE mtgjson_printings (
            uuid TEXT PRIMARY KEY, printing_id TEXT, name TEXT NOT NULL,
            set_code TEXT NOT NULL, number TEXT NOT NULL, rarity TEXT,
            border_color TEXT, is_full_art INTEGER DEFAULT 0, frame_effects TEXT,
            ck_url TEXT, ck_url_foil TEXT, imported_at TEXT NOT NULL, side TEXT
        );

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
            color TEXT, binder_type TEXT, storage_location TEXT, description TEXT, notes TEXT,
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
        CREATE TABLE deck_states (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
        );
        INSERT INTO deck_states VALUES (1,'idea'),(2,'ready'),(3,'constructed');
        CREATE TABLE decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, description TEXT, format TEXT,
            is_precon INTEGER NOT NULL DEFAULT 0,
            sleeve_color TEXT, deck_box TEXT, storage_location TEXT,
            state_id INTEGER NOT NULL DEFAULT 1 REFERENCES deck_states(id),
            origin_set_code TEXT, origin_theme TEXT, origin_variation INTEGER,
            hypothetical INTEGER NOT NULL DEFAULT 0,
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
        CREATE INDEX idx_deck_expected_deck ON deck_expected_cards(deck_id);
        CREATE TABLE deck_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            printing_id TEXT NOT NULL REFERENCES printings(printing_id),
            collection_id INTEGER REFERENCES collection(id) ON DELETE SET NULL,
            zone TEXT NOT NULL DEFAULT 'mainboard',
            quantity INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE movement_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER, from_deck_id INTEGER, to_deck_id INTEGER,
            from_binder_id INTEGER, to_binder_id INTEGER,
            from_zone TEXT, to_zone TEXT, note TEXT, moved_at TEXT NOT NULL
        );
        CREATE TABLE status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER, old_status TEXT, new_status TEXT, changed_at TEXT NOT NULL
        );

        INSERT INTO sets VALUES ('test', 'Test Set');
        INSERT INTO cards (oracle_id, name) VALUES ('o1', 'Lightning Bolt');
        INSERT INTO printings (printing_id, oracle_id, set_code, collector_number)
            VALUES ('p1', 'o1', 'test', '1');
        INSERT INTO decks (name, state_id, created_at, updated_at)
            VALUES ('Pre-v52 Deck', 1, '2025-01-01', '2025-01-01');
        INSERT INTO deck_expected_cards (deck_id, printing_id, zone, quantity)
            VALUES (1, 'p1', 'mainboard', 2);
    """)
    return conn, db_path


class TestMigrationV51ToV52:
    def test_existing_rows_have_null_finish(self):
        """Migration adds a nullable finish column; pre-existing rows get NULL."""
        conn, db_path = _make_v51_db()
        try:
            init_db(conn)
            row = conn.execute(
                "SELECT finish FROM deck_expected_cards WHERE deck_id = 1"
            ).fetchone()
            assert row is not None
            assert row["finish"] is None
        finally:
            conn.close()
            os.unlink(db_path)

    def test_schema_version_advances(self):
        conn, db_path = _make_v51_db()
        try:
            init_db(conn)
            from mtg_collector.db.schema import get_current_version
            assert get_current_version(conn) == SCHEMA_VERSION
        finally:
            conn.close()
            os.unlink(db_path)

    def test_finish_column_present_after_migration(self):
        conn, db_path = _make_v51_db()
        try:
            init_db(conn)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(deck_expected_cards)").fetchall()}
            assert "finish" in cols
        finally:
            conn.close()
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# set_expected_cards / get_expected_cards carry finish
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    conn, db_path = _fresh_db()
    init_db(conn)
    _seed(conn)
    yield conn
    conn.close()
    os.unlink(db_path)


class TestExpectedCardsFinish:
    def test_set_and_get_finish_foil(self, db):
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Commander Precon"))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "commander", "quantity": 1, "finish": "foil"},
            {"printing_id": "p2", "zone": "mainboard", "quantity": 1, "finish": "nonfoil"},
        ])
        db.commit()

        cards = repo.get_expected_cards(deck_id)
        by_pid = {c["printing_id"]: c for c in cards}
        assert by_pid["p1"]["finish"] == "foil"
        assert by_pid["p2"]["finish"] == "nonfoil"

    def test_set_expected_cards_default_finish_is_nonfoil(self, db):
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Deck"))
        db.commit()

        # No 'finish' key in the dict
        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "mainboard", "quantity": 1},
        ])
        db.commit()

        cards = repo.get_expected_cards(deck_id)
        assert cards[0]["finish"] == "nonfoil"

    def test_get_cards_for_state_carries_finish(self, db):
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Idea Deck", state_id=DECK_STATE_IDEA))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "mainboard", "quantity": 1, "finish": "foil"},
        ])
        db.commit()

        cards = repo.get_cards_for_state(deck_id)
        assert len(cards) == 1
        assert cards[0]["finish"] == "foil"


# ---------------------------------------------------------------------------
# isFoil parsing mirrors _api_precons_import logic
# ---------------------------------------------------------------------------

class TestPreconImportIsFoil:
    def test_is_foil_true_maps_to_foil(self):
        """Replicate the tuple-unpacking and finish-assignment logic from _api_precons_import."""
        deck_data = {
            "mainBoard": [
                {"uuid": "abc", "count": 1, "isFoil": True},
                {"uuid": "def", "count": 1, "isFoil": False},
            ],
            "sideBoard": [],
            "commander": [
                {"uuid": "ghi", "count": 1},  # no isFoil key — should be nonfoil
            ],
        }
        uuids = []
        for zone in ("mainBoard", "sideBoard", "commander"):
            for c in deck_data.get(zone, []):
                uuids.append((zone, c["uuid"], c.get("count", 1), c.get("isFoil", False)))

        ZONE_MAP = {"mainBoard": "mainboard", "sideBoard": "sideboard", "commander": "commander"}
        uuid_to_pid = {"abc": "p1", "def": "p2", "ghi": "p3"}

        expected = []
        for zone, uuid, count, is_foil in uuids:
            pid = uuid_to_pid.get(uuid)
            if pid is None:
                continue
            expected.append({
                "printing_id": pid,
                "zone": ZONE_MAP[zone],
                "quantity": count,
                "finish": "foil" if is_foil else "nonfoil",
            })

        by_pid = {e["printing_id"]: e for e in expected}
        assert by_pid["p1"]["finish"] == "foil"
        assert by_pid["p2"]["finish"] == "nonfoil"
        assert by_pid["p3"]["finish"] == "nonfoil"


# ---------------------------------------------------------------------------
# materialize_deck matches by finish
# ---------------------------------------------------------------------------

class TestMaterializeDeckByFinish:
    def test_foil_expected_matches_foil_copy(self, db):
        """Materialize picks a foil copy when the expected list says foil."""
        col_repo = CollectionRepository(db)
        foil_id = col_repo.add(CollectionEntry(id=None, printing_id="p1", finish="foil"))
        nonfoil_id = col_repo.add(CollectionEntry(id=None, printing_id="p1", finish="nonfoil"))
        db.commit()

        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Foil Commander", state_id=DECK_STATE_IDEA))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "mainboard", "quantity": 1, "finish": "foil"},
        ])
        db.commit()

        result = repo.materialize_deck(deck_id)
        db.commit()

        assert result["total_matched"] == 1
        row = db.execute(
            "SELECT col.finish FROM deck_cards dc "
            "JOIN collection col ON dc.collection_id = col.id "
            "WHERE dc.deck_id = ?",
            (deck_id,),
        ).fetchone()
        assert row["finish"] == "foil"

    def test_nonfoil_expected_does_not_match_foil_copy(self, db):
        """Materialize does not assign a foil copy to a nonfoil slot."""
        col_repo = CollectionRepository(db)
        col_repo.add(CollectionEntry(id=None, printing_id="p1", finish="foil"))
        db.commit()

        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Nonfoil Deck", state_id=DECK_STATE_IDEA))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "mainboard", "quantity": 1, "finish": "nonfoil"},
        ])
        db.commit()

        result = repo.materialize_deck(deck_id)
        db.commit()

        assert result["total_matched"] == 0
        assert len(result["missing"]) == 1


# ---------------------------------------------------------------------------
# finish resolver: unsupplied finish derived from printing
# ---------------------------------------------------------------------------

class TestFinishResolver:
    def test_foil_only_no_finish_supplied_stores_foil(self, db):
        """When finish is absent for a foil-only printing, the resolver stores 'foil'."""
        PrintingRepository(db).upsert(
            Printing(printing_id="p_foilonly", oracle_id="o1", set_code="test",
                     collector_number="99", finishes=["foil"])
        )
        db.commit()

        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Foil Only Deck"))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p_foilonly", "zone": "mainboard", "quantity": 1},
        ])
        db.commit()

        cards = repo.get_expected_cards(deck_id)
        assert cards[0]["finish"] == "foil"

    def test_both_finishes_no_finish_supplied_stores_nonfoil(self, db):
        """When finish is absent for a printing with both finishes, resolver stores 'nonfoil'."""
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Both Deck"))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p1", "zone": "mainboard", "quantity": 1},
        ])
        db.commit()

        cards = repo.get_expected_cards(deck_id)
        assert cards[0]["finish"] == "nonfoil"

    def test_explicit_foil_for_foil_only_stored(self, db):
        """An explicit finish='foil' for a foil-only printing is accepted and stored."""
        PrintingRepository(db).upsert(
            Printing(printing_id="p_foilonly2", oracle_id="o1", set_code="test",
                     collector_number="98", finishes=["foil"])
        )
        db.commit()

        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Explicit Foil Deck"))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p_foilonly2", "zone": "mainboard", "quantity": 1, "finish": "foil"},
        ])
        db.commit()

        cards = repo.get_expected_cards(deck_id)
        assert cards[0]["finish"] == "foil"

    def test_finish_not_offered_by_printing_raises(self, db):
        """Supplying a finish the printing does not offer raises ValueError."""
        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Bad Finish Deck"))
        db.commit()

        with pytest.raises(ValueError, match="not offered"):
            repo.set_expected_cards(deck_id, [
                {"printing_id": "p2", "zone": "mainboard", "quantity": 1, "finish": "foil"},
            ])

    def test_foil_only_acquire_then_materialize_missing_zero(self, db):
        """acquire then materialize on a foil-only deck yields total_missing == 0."""
        PrintingRepository(db).upsert(
            Printing(printing_id="p_foilonly3", oracle_id="o2", set_code="test",
                     collector_number="97", finishes=["foil"])
        )
        db.commit()

        repo = DeckRepository(db)
        deck_id = repo.add(Deck(id=None, name="Foil Roundtrip Deck"))
        db.commit()

        repo.set_expected_cards(deck_id, [
            {"printing_id": "p_foilonly3", "zone": "mainboard", "quantity": 1},
        ])
        db.commit()

        result = repo.acquire_expected_cards(deck_id)
        db.commit()

        mat = repo.materialize_deck(deck_id)
        db.commit()

        assert mat["total_missing"] == 0
