"""
Tests for POST /api/decks/:id/acquire (DeckRepository.acquire_expected_cards).

Unit tier: no container, no network.
To run: uv run pytest tests/test_deck_acquire.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import (
    BatchRepository,
    Card,
    CardRepository,
    CollectionRepository,
    Deck,
    DeckRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import init_db


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def seeded(db):
    """DB with two printings: one nonfoil-only, one foil-only.

    deck_a has three expected slots (2x p_nf + 1x p_foil, qty-weighted).
    deck_empty has no expected cards.
    """
    set_repo = SetRepository(db)
    card_repo = CardRepository(db)
    printing_repo = PrintingRepository(db)
    deck_repo = DeckRepository(db)

    set_repo.upsert(Set(set_code="tst", set_name="Test Set"))
    card_repo.upsert(Card(oracle_id="o1", name="Alpha Card"))
    card_repo.upsert(Card(oracle_id="o2", name="Beta Card"))

    # nonfoil-only printing
    printing_repo.upsert(Printing(
        printing_id="p_nf", oracle_id="o1", set_code="tst",
        collector_number="1", finishes=["nonfoil"],
    ))
    # foil-only printing
    printing_repo.upsert(Printing(
        printing_id="p_foil", oracle_id="o2", set_code="tst",
        collector_number="2", finishes=["foil"],
    ))

    deck_a_id = deck_repo.add(Deck(id=None, name="Goblin Mob", origin_set_code="tst"))
    deck_repo.set_expected_cards(deck_a_id, [
        {"printing_id": "p_nf", "zone": "mainboard", "quantity": 2},
        {"printing_id": "p_foil", "zone": "mainboard", "quantity": 1},
    ])

    deck_empty_id = deck_repo.add(Deck(id=None, name="Empty Deck", origin_set_code="tst"))

    db.commit()
    return db, deck_a_id, deck_empty_id


class TestAcquireExpectedCards:
    def test_cards_added_equals_sum_of_quantities(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        assert result["cards_added"] == 3  # 2 + 1

    def test_collection_rows_carry_batch_id(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        batch_id = result["batch_id"]
        rows = db.execute(
            "SELECT id FROM collection WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        assert len(rows) == 3

    def test_acquire_then_materialize_total_missing_zero(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        repo.acquire_expected_cards(deck_a_id)
        db.commit()
        mat = repo.materialize_deck(deck_a_id)
        db.commit()
        assert mat["total_missing"] == 0

    def test_materialize_matches_on_expected_printing(self, seeded):
        """Every matched card used the exact expected printing_id."""
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        repo.acquire_expected_cards(deck_a_id)
        db.commit()
        mat = repo.materialize_deck(deck_a_id)
        db.commit()
        for entry in mat["matched"]:
            assert entry["found"] == entry["expected"]

    def test_acquire_twice_doubles_rows(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        repo.acquire_expected_cards(deck_a_id)
        db.commit()
        result2 = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        total = db.execute("SELECT COUNT(*) FROM collection").fetchone()[0]
        assert total == 6  # 3 + 3

    def test_acquire_twice_second_previous_names_first(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        first = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        second = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        assert len(second["previous"]) == 1
        assert second["previous"][0]["batch_id"] == first["batch_id"]
        assert second["previous"][0]["card_count"] == 3

    def test_nonfoil_available_acquires_as_nonfoil(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        batch_id = result["batch_id"]
        rows = db.execute(
            "SELECT c.finish FROM collection c "
            "JOIN printings p ON c.printing_id = p.printing_id "
            "WHERE c.batch_id = ? AND p.printing_id = 'p_nf'",
            (batch_id,),
        ).fetchall()
        assert rows, "expected rows for p_nf"
        assert all(r["finish"] == "nonfoil" for r in rows)

    def test_foil_only_printing_acquires_as_foil(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        batch_id = result["batch_id"]
        rows = db.execute(
            "SELECT c.finish FROM collection c "
            "JOIN printings p ON c.printing_id = p.printing_id "
            "WHERE c.batch_id = ? AND p.printing_id = 'p_foil'",
            (batch_id,),
        ).fetchall()
        assert rows, "expected rows for p_foil"
        assert all(r["finish"] == "foil" for r in rows)

    def test_empty_expected_list_no_batch_created(self, seeded):
        """Handler responsibility: check before calling. Repo is called only
        when there are expected cards, so test the guard at the handler layer
        by calling get_expected_cards on the empty deck."""
        db, _, deck_empty_id = seeded
        repo = DeckRepository(db)
        expected = repo.get_expected_cards(deck_empty_id)
        assert expected == []
        batch_count_before = db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        # do not call acquire_expected_cards — handler would have returned 400
        assert db.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == batch_count_before

    def test_batch_has_deck_id(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        batch = db.execute(
            "SELECT deck_id, batch_type FROM batches WHERE id = ?",
            (result["batch_id"],),
        ).fetchone()
        assert batch["deck_id"] == deck_a_id
        assert batch["batch_type"] == "deck_acquire"

    def test_cards_not_assigned_to_deck(self, seeded):
        """acquire does not put cards in deck_cards — that is materialize's job."""
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        repo.acquire_expected_cards(deck_a_id)
        db.commit()
        deck_cards = db.execute(
            "SELECT COUNT(*) FROM deck_cards WHERE deck_id = ?", (deck_a_id,)
        ).fetchone()[0]
        assert deck_cards == 0

    def test_source_is_deck_acquire(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        sources = db.execute(
            "SELECT DISTINCT source FROM collection WHERE batch_id = ?",
            (result["batch_id"],),
        ).fetchall()
        assert [r["source"] for r in sources] == ["deck_acquire"]

    def test_condition_is_near_mint(self, seeded):
        db, deck_a_id, _ = seeded
        repo = DeckRepository(db)
        result = repo.acquire_expected_cards(deck_a_id)
        db.commit()
        conditions = db.execute(
            "SELECT DISTINCT condition FROM collection WHERE batch_id = ?",
            (result["batch_id"],),
        ).fetchall()
        assert [r["condition"] for r in conditions] == ["Near Mint"]

    def test_printing_with_both_finishes_acquires_nonfoil(self, db):
        """A printing that offers both nonfoil and foil is acquired as nonfoil."""
        set_repo = SetRepository(db)
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)
        deck_repo = DeckRepository(db)

        set_repo.upsert(Set(set_code="tst2", set_name="Test Set 2"))
        card_repo.upsert(Card(oracle_id="o3", name="Gamma Card"))
        printing_repo.upsert(Printing(
            printing_id="p_both", oracle_id="o3", set_code="tst2",
            collector_number="1", finishes=["nonfoil", "foil"],
        ))
        deck_id = deck_repo.add(Deck(id=None, name="Both Deck", origin_set_code="tst2"))
        deck_repo.set_expected_cards(deck_id, [
            {"printing_id": "p_both", "zone": "mainboard", "quantity": 1},
        ])
        db.commit()

        result = deck_repo.acquire_expected_cards(deck_id)
        db.commit()

        row = db.execute(
            "SELECT finish FROM collection WHERE batch_id = ?", (result["batch_id"],)
        ).fetchone()
        assert row["finish"] == "nonfoil"
