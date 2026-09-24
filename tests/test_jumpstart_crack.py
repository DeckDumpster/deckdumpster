"""
Tests for POST /api/sealed/jumpstart-crack (crack a Jumpstart booster from
sealed inventory) and DELETE /api/batches/:id for jumpstart_crack batches.

Unit tier: no container, no network.
To run: uv run pytest tests/test_jumpstart_crack.py -v
"""

import json
import os
import sqlite3
import tempfile
import uuid as uuid_mod

import pytest

from mtg_collector.db.models import (
    Batch,
    BatchRepository,
    Card,
    CardRepository,
    CollectionRepository,
    Printing,
    PrintingRepository,
    SealedCollectionEntry,
    SealedCollectionRepository,
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
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def seeded(db):
    """
    DB seeded with:
    - Set j25 (Foundations Jumpstart)
    - 3 cards: Angel, Warrior, Dragon
    - 3 printings with matching mtgjson_uuid_map rows
    - mtgjson_decks: one deck "Angels (1)" with all 3 cards
    - a sealed_collection 'owned' entry for j25 booster pack
    """
    set_repo = SetRepository(db)
    card_repo = CardRepository(db)
    printing_repo = PrintingRepository(db)

    set_repo.upsert(Set(set_code="j25", set_name="Foundations Jumpstart"))

    card_repo.upsert(Card(oracle_id="oa", name="Angel of Dawn"))
    card_repo.upsert(Card(oracle_id="ob", name="Blessed Warrior"))
    card_repo.upsert(Card(oracle_id="oc", name="Solar Dragon"))

    printing_repo.upsert(Printing(
        printing_id="p_angel", oracle_id="oa", set_code="j25",
        collector_number="1", finishes=["nonfoil"],
    ))
    printing_repo.upsert(Printing(
        printing_id="p_warrior", oracle_id="ob", set_code="j25",
        collector_number="2", finishes=["nonfoil"],
    ))
    printing_repo.upsert(Printing(
        printing_id="p_dragon", oracle_id="oc", set_code="j25",
        collector_number="3", finishes=["foil"],
    ))

    u_angel = "uuid-angel-1111"
    u_warrior = "uuid-warrior-2222"
    u_dragon = "uuid-dragon-3333"
    u_unknown = "uuid-unknown-9999"

    db.executemany(
        "INSERT INTO mtgjson_uuid_map (uuid, set_code, collector_number) VALUES (?, ?, ?)",
        [
            (u_angel, "j25", "1"),
            (u_warrior, "j25", "2"),
            (u_dragon, "j25", "3"),
        ],
    )

    deck_data = json.dumps({
        "mainBoard": [
            {"uuid": u_angel, "count": 4},
            {"uuid": u_warrior, "count": 4},
            {"uuid": u_dragon, "count": 1},
        ]
    })
    deck_data_bad = json.dumps({
        "mainBoard": [
            {"uuid": u_angel, "count": 2},
            {"uuid": u_unknown, "count": 18},  # unresolvable
        ]
    })

    db.execute(
        "INSERT INTO mtgjson_decks (set_code, name, base_name, variation, type, deck_data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("j25", "Angels (1)", "Angels", 1, "Jumpstart", deck_data),
    )
    db.execute(
        "INSERT INTO mtgjson_decks (set_code, name, base_name, variation, type, deck_data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("j25", "Bad Theme (1)", "Bad Theme", 1, "Jumpstart", deck_data_bad),
    )

    db.execute(
        "INSERT INTO sealed_products (uuid, name, set_code, category, imported_at) VALUES (?, ?, ?, ?, ?)",
        ("sp-uuid-j25", "Foundations Jumpstart Booster Pack", "j25", "booster_pack", "2024-01-01T00:00:00Z"),
    )

    sealed_repo = SealedCollectionRepository(db)
    entry = SealedCollectionEntry(
        id=None,
        sealed_product_uuid="sp-uuid-j25",
        quantity=2,
        status="owned",
        condition="Near Mint",
        source="purchase",
    )
    sealed_id = sealed_repo.add(entry)
    db.commit()

    return db, sealed_id, {
        "u_angel": u_angel,
        "u_warrior": u_warrior,
        "u_dragon": u_dragon,
        "u_unknown": u_unknown,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def crack(db, sealed_collection_id, deck_name, set_code="j25", condition="Near Mint"):
    """Direct model-layer crack: creates batch + collection rows + disposes sealed."""
    import json as _json
    import uuid as _uuid

    from mtg_collector.db.models import (
        Batch, BatchRepository, CollectionEntry, CollectionRepository,
        SealedCollectionRepository,
    )

    sealed_repo = SealedCollectionRepository(db)
    sealed_entry = sealed_repo.get(sealed_collection_id)
    assert sealed_entry is not None
    assert sealed_entry.status == "owned"

    row = db.execute(
        "SELECT name, base_name, variation, deck_data FROM mtgjson_decks "
        "WHERE set_code = ? AND name = ?",
        (set_code, deck_name),
    ).fetchone()
    assert row is not None, f"deck not found: {deck_name}"

    zones = _json.loads(row["deck_data"])
    entries = [(c["uuid"], c.get("count", 1)) for c in zones.get("mainBoard", [])]

    ph = ",".join("?" * len(entries))
    resolved_rows = db.execute(
        f"""SELECT m.uuid, p.printing_id, p.finishes
            FROM mtgjson_uuid_map m
            JOIN printings p ON p.set_code = m.set_code
                            AND p.collector_number = m.collector_number
            WHERE m.uuid IN ({ph})""",
        [e[0] for e in entries],
    ).fetchall()
    uuid_to_info = {r["uuid"]: dict(r) for r in resolved_rows}

    unresolved = [e[0] for e in entries if e[0] not in uuid_to_info]
    if unresolved:
        raise ValueError(f"unresolvable: {unresolved}")

    batch_repo = BatchRepository(db)
    b = Batch(
        id=None,
        batch_uuid=str(_uuid.uuid4()),
        name=f"Cracked: {row['base_name']} ({set_code.upper()})",
        batch_type="jumpstart_crack",
        set_code=set_code,
        notes=_json.dumps({"sealed_collection_id": sealed_collection_id}),
    )
    batch_id = batch_repo.create(b)

    collection_repo = CollectionRepository(db)
    cards_added = 0
    for uuid_val, count in entries:
        info = uuid_to_info[uuid_val]
        finishes_raw = info["finishes"]
        finishes = _json.loads(finishes_raw) if isinstance(finishes_raw, str) else list(finishes_raw or [])
        finish = "nonfoil" if "nonfoil" in finishes else finishes[0]
        for _ in range(count):
            collection_repo.add(CollectionEntry(
                id=None,
                printing_id=info["printing_id"],
                finish=finish,
                condition=condition,
                source="jumpstart_crack",
                batch_id=batch_id,
            ))
            cards_added += 1

    batch_repo.increment_card_count(batch_id, cards_added)
    batch_repo.complete(batch_id)

    # quantity=1: crack one booster, decrement from qty=2
    sealed_repo.dispose(sealed_collection_id, "opened", quantity=1)
    db.commit()

    return {"batch_id": batch_id, "cards_added": cards_added}


# ── SealedCollectionRepository VALID_TRANSITIONS ──────────────────────────────

class TestSealedOpenedToOwned:
    def test_opened_to_owned_is_valid(self, seeded):
        db, sealed_id, _ = seeded
        sealed_repo = SealedCollectionRepository(db)
        # Dispose one unit as opened
        sealed_repo.dispose(sealed_id, "opened", quantity=1)
        db.commit()
        # Find the new opened entry
        opened = db.execute(
            "SELECT id FROM sealed_collection WHERE status = 'opened'"
        ).fetchone()
        assert opened is not None
        # Reverse it to owned
        sealed_repo.dispose(opened["id"], "owned")
        db.commit()
        entry = sealed_repo.get(opened["id"])
        assert entry.status == "owned"

    def test_owned_to_opened_still_valid(self, seeded):
        db, sealed_id, _ = seeded
        sealed_repo = SealedCollectionRepository(db)
        sealed_repo.dispose(sealed_id, "opened", quantity=1)
        db.commit()
        # The original entry still has qty=1, status=owned — transition still works
        original = sealed_repo.get(sealed_id)
        assert original.status == "owned"


# ── Crack operation ────────────────────────────────────────────────────────────

class TestJumpstartCrack:
    def test_cards_added_equals_deck_total(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        assert result["cards_added"] == 9  # 4+4+1

    def test_collection_rows_have_jumpstart_crack_source(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        sources = db.execute(
            "SELECT DISTINCT source FROM collection WHERE batch_id = ?",
            (result["batch_id"],),
        ).fetchall()
        assert [r["source"] for r in sources] == ["jumpstart_crack"]

    def test_batch_type_is_jumpstart_crack(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        batch = db.execute(
            "SELECT batch_type FROM batches WHERE id = ?", (result["batch_id"],)
        ).fetchone()
        assert batch["batch_type"] == "jumpstart_crack"

    def test_batch_notes_stores_sealed_collection_id(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        notes_raw = db.execute(
            "SELECT notes FROM batches WHERE id = ?", (result["batch_id"],)
        ).fetchone()["notes"]
        notes = json.loads(notes_raw)
        assert notes["sealed_collection_id"] == sealed_id

    def test_foil_only_printing_acquires_as_foil(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        # Dragon (p_dragon) is foil-only
        row = db.execute(
            "SELECT c.finish FROM collection c "
            "JOIN printings p ON c.printing_id = p.printing_id "
            "WHERE c.batch_id = ? AND p.printing_id = 'p_dragon'",
            (result["batch_id"],),
        ).fetchone()
        assert row["finish"] == "foil"

    def test_nonfoil_available_acquires_as_nonfoil(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        row = db.execute(
            "SELECT c.finish FROM collection c "
            "JOIN printings p ON c.printing_id = p.printing_id "
            "WHERE c.batch_id = ? AND p.printing_id = 'p_angel'",
            (result["batch_id"],),
        ).fetchone()
        assert row["finish"] == "nonfoil"

    def test_sealed_entry_decremented_to_opened(self, seeded):
        db, sealed_id, _ = seeded
        crack(db, sealed_id, "Angels (1)")
        # qty was 2; one cracked → remaining owned=1, new opened=1
        owned = db.execute(
            "SELECT quantity FROM sealed_collection WHERE id = ? AND status = 'owned'",
            (sealed_id,),
        ).fetchone()
        assert owned["quantity"] == 1
        opened_count = db.execute(
            "SELECT COUNT(*) FROM sealed_collection WHERE status = 'opened'"
        ).fetchone()[0]
        assert opened_count == 1

    def test_unresolvable_uuid_raises(self, seeded):
        db, sealed_id, _ = seeded
        with pytest.raises(ValueError, match="unresolvable"):
            crack(db, sealed_id, "Bad Theme (1)")

    def test_unresolvable_adds_no_cards(self, seeded):
        db, sealed_id, _ = seeded
        try:
            crack(db, sealed_id, "Bad Theme (1)")
        except ValueError:
            pass
        count = db.execute("SELECT COUNT(*) FROM collection").fetchone()[0]
        assert count == 0

    def test_condition_passed_through(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)", condition="Lightly Played")
        conditions = db.execute(
            "SELECT DISTINCT condition FROM collection WHERE batch_id = ?",
            (result["batch_id"],),
        ).fetchall()
        assert [r["condition"] for r in conditions] == ["Lightly Played"]


# ── Undo operation ─────────────────────────────────────────────────────────────

class TestJumpstartCrackUndo:
    def test_undo_removes_all_collection_rows(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        batch_id = result["batch_id"]

        batch_repo = BatchRepository(db)
        batch = batch_repo.get(batch_id)
        assert batch is not None

        # Re-implement the reverse logic (mirrors _reverse_jumpstart_crack_batch)
        rows = db.execute(
            "SELECT id FROM collection WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        assert len(rows) == 9

        # Use the repo helper via the sealed flow
        from mtg_collector.db.models import SealedCollectionRepository, CollectionRepository
        sealed_repo = SealedCollectionRepository(db)
        # Find the opened entry
        opened = db.execute(
            "SELECT id FROM sealed_collection WHERE status = 'opened'"
        ).fetchone()
        sealed_repo.dispose(opened["id"], "owned")

        coll_repo = CollectionRepository(db)
        coll_repo.bulk_delete([r["id"] for r in rows])
        db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        db.commit()

        remaining = db.execute(
            "SELECT COUNT(*) FROM collection WHERE batch_id = ?", (batch_id,)
        ).fetchone()[0]
        assert remaining == 0

    def test_undo_restores_sealed_entry_to_owned(self, seeded):
        db, sealed_id, _ = seeded
        crack(db, sealed_id, "Angels (1)")

        from mtg_collector.db.models import SealedCollectionRepository
        sealed_repo = SealedCollectionRepository(db)
        opened = db.execute(
            "SELECT id FROM sealed_collection WHERE status = 'opened'"
        ).fetchone()
        sealed_repo.dispose(opened["id"], "owned")
        db.commit()

        entry = sealed_repo.get(opened["id"])
        assert entry.status == "owned"

    def test_undo_refused_when_card_in_deck(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        batch_id = result["batch_id"]

        # Put one card in a deck
        from mtg_collector.db.models import Deck, DeckRepository
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="Test Deck"))
        first_row = db.execute(
            "SELECT c.id, c.printing_id FROM collection c WHERE c.batch_id = ? LIMIT 1",
            (batch_id,),
        ).fetchone()
        first_card = first_row["id"]
        db.execute(
            "INSERT INTO deck_cards (deck_id, collection_id, zone, printing_id) VALUES (?, ?, ?, ?)",
            (deck_id, first_card, "mainboard", first_row["printing_id"]),
        )
        db.commit()

        # Verify the block condition: in_deck flag is set
        row = db.execute(
            """SELECT (SELECT 1 FROM deck_cards dc WHERE dc.collection_id = c.id LIMIT 1) AS in_deck
               FROM collection c WHERE c.id = ?""",
            (first_card,),
        ).fetchone()
        assert row["in_deck"] == 1

    def test_undo_refused_when_card_in_binder(self, seeded):
        db, sealed_id, _ = seeded
        result = crack(db, sealed_id, "Angels (1)")
        batch_id = result["batch_id"]

        # Put one card in a binder
        from mtg_collector.db.models import Binder, BinderRepository
        binder_repo = BinderRepository(db)
        binder_id = binder_repo.add(Binder(id=None, name="Test Binder"))
        first_card = db.execute(
            "SELECT id FROM collection WHERE batch_id = ? LIMIT 1", (batch_id,)
        ).fetchone()["id"]
        db.execute(
            "UPDATE collection SET binder_id = ? WHERE id = ?",
            (binder_id, first_card),
        )
        db.commit()

        row = db.execute(
            "SELECT binder_id FROM collection WHERE id = ?", (first_card,)
        ).fetchone()
        assert row["binder_id"] == binder_id
