"""
Tests for single-card ingest via image_id parameter in batch-ingest.

Verifies that passing image_id to batch-ingest only processes that specific
image, leaving other DONE images untouched.

To run: uv run pytest tests/test_single_card_ingest.py -v
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
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import init_db
from mtg_collector.utils import now_iso


@pytest.fixture
def db():
    """Create a fresh database with schema and test printings."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Seed card data
    set_repo = SetRepository(conn)
    card_repo = CardRepository(conn)
    printing_repo = PrintingRepository(conn)

    set_repo.upsert(Set(set_code="tst", set_name="Test Set"))
    card_repo.upsert(Card(oracle_id="oracle-a", name="Card A"))
    card_repo.upsert(Card(oracle_id="oracle-b", name="Card B"))
    printing_repo.upsert(
        Printing(printing_id="pa", oracle_id="oracle-a", set_code="tst", collector_number="1")
    )
    printing_repo.upsert(
        Printing(printing_id="pb", oracle_id="oracle-b", set_code="tst", collector_number="2")
    )

    # Insert two DONE ingest images
    ts = "2026-01-01T00:00:00Z"
    conn.execute(
        """INSERT INTO ingest_images (id, filename, stored_name, md5, status, disambiguated, confirmed_finishes, created_at, updated_at)
           VALUES (1, 'a.jpg', 'a.jpg', 'md5_a', 'DONE', ?, ?, ?, ?)""",
        (json.dumps(["pa"]), json.dumps(["nonfoil"]), ts, ts),
    )
    conn.execute(
        """INSERT INTO ingest_images (id, filename, stored_name, md5, status, disambiguated, confirmed_finishes, created_at, updated_at)
           VALUES (2, 'b.jpg', 'b.jpg', 'md5_b', 'DONE', ?, ?, ?, ?)""",
        (json.dumps(["pb"]), json.dumps(["nonfoil"]), ts, ts),
    )
    conn.commit()

    yield conn, db_path

    conn.close()
    os.unlink(db_path)


def _run_batch_ingest(conn, image_id=None, assign_target=""):
    """Simulate the batch-ingest handler logic (mirrors crack_pack_server.py).

    This must stay in sync with _api_ingest2_batch_ingest in crack_pack_server.py.
    The image_id filtering is the feature under test.
    """
    from mtg_collector.cli.crack_pack_server import _batch_ingest_query

    rows = conn.execute(*_batch_ingest_query(image_id)).fetchall()

    printing_repo = PrintingRepository(conn)
    collection_repo = CollectionRepository(conn)
    count = 0
    batch_collection_ids = []

    for row in rows:
        img = dict(row)
        disambiguated = json.loads(img["disambiguated"]) if img.get("disambiguated") else []

        for card_idx, sid in enumerate(disambiguated):
            if not sid or sid in ("skipped", "already_ingested"):
                continue
            existing = conn.execute(
                "SELECT 1 FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?",
                (img["md5"], card_idx),
            ).fetchone()
            if existing:
                continue
            printing = printing_repo.get(sid)
            if not printing:
                continue
            confirmed = json.loads(img["confirmed_finishes"]) if img.get("confirmed_finishes") else []
            finish = None
            if card_idx < len(confirmed) and confirmed[card_idx]:
                finish = confirmed[card_idx]
            if not finish:
                finishes = (
                    json.loads(printing.raw_json).get("finishes", ["nonfoil"])
                    if printing.raw_json
                    else ["nonfoil"]
                )
                finish = finishes[0] if finishes else "nonfoil"
            entry = CollectionEntry(
                id=None,
                printing_id=sid,
                finish=finish,
                condition="Near Mint",
                source="ocr_ingest",
            )
            entry_id = collection_repo.add(entry)
            batch_collection_ids.append(entry_id)
            conn.execute(
                """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (entry_id, img["md5"], img["stored_name"], card_idx, now_iso()),
            )

        conn.execute(
            "UPDATE ingest_images SET status = 'INGESTED' WHERE id = ?",
            (img["id"],),
        )
        count += 1

    conn.commit()
    return {"ok": True, "count": count, "collection_ids": batch_collection_ids}


class TestSingleCardIngest:
    """Test that image_id parameter scopes batch-ingest to a single image."""

    def test_batch_ingest_without_image_id_processes_all(self, db):
        """Without image_id, all DONE images are ingested."""
        conn, _ = db
        result = _run_batch_ingest(conn)
        assert result["count"] == 2
        assert len(result["collection_ids"]) == 2

        # Both images should be INGESTED
        statuses = conn.execute(
            "SELECT id, status FROM ingest_images ORDER BY id"
        ).fetchall()
        assert dict(statuses[0])["status"] == "INGESTED"
        assert dict(statuses[1])["status"] == "INGESTED"

    def test_batch_ingest_with_image_id_processes_only_that_image(self, db):
        """With image_id, only the specified image is ingested."""
        conn, _ = db
        result = _run_batch_ingest(conn, image_id=1)
        assert result["count"] == 1
        assert len(result["collection_ids"]) == 1

        # Only image 1 should be INGESTED, image 2 still DONE
        statuses = conn.execute(
            "SELECT id, status FROM ingest_images ORDER BY id"
        ).fetchall()
        assert dict(statuses[0])["status"] == "INGESTED"
        assert dict(statuses[1])["status"] == "DONE"

        # The ingested card should be "pa" (Card A)
        lineage = conn.execute("SELECT image_md5 FROM ingest_lineage").fetchall()
        assert len(lineage) == 1
        assert lineage[0]["image_md5"] == "md5_a"

    def test_batch_ingest_with_image_id_then_remaining(self, db):
        """After single-card ingest, batch ingest picks up the rest."""
        conn, _ = db
        # Ingest just image 1
        result1 = _run_batch_ingest(conn, image_id=1)
        assert result1["count"] == 1

        # Now ingest remaining (no image_id)
        result2 = _run_batch_ingest(conn)
        assert result2["count"] == 1

        # Both should now be INGESTED
        statuses = conn.execute(
            "SELECT id, status FROM ingest_images ORDER BY id"
        ).fetchall()
        assert dict(statuses[0])["status"] == "INGESTED"
        assert dict(statuses[1])["status"] == "INGESTED"

    def test_batch_ingest_with_nonexistent_image_id(self, db):
        """image_id pointing to non-existent image processes nothing."""
        conn, _ = db
        result = _run_batch_ingest(conn, image_id=999)
        assert result["count"] == 0
        assert len(result["collection_ids"]) == 0

        # Both images remain DONE
        statuses = conn.execute(
            "SELECT id, status FROM ingest_images ORDER BY id"
        ).fetchall()
        assert dict(statuses[0])["status"] == "DONE"
        assert dict(statuses[1])["status"] == "DONE"
