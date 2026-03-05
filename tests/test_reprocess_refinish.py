"""
Tests for Reprocess and Refinish actions (issue #172).

Reprocess: reset an image fully and re-run it through the Agent pipeline.
Refinish: remove collection entry but keep Agent results, so the user can
  re-select the finish on the Recents page.

These are unit tests against the server helpers and DB state, not full HTTP tests.
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from mtg_collector.db.schema import init_db

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"
BRIMSTONE_IMAGE = Path(__file__).parent / "fixtures" / "sample-brimstone-mage.jpg"
BRIMSTONE_MD5 = "d6e51a55cb0d624587ae3ea8ddb6d360"


@pytest.fixture
def db():
    """Create a temp DB from the test fixture with ingest tables populated."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    if FIXTURE_DB.exists():
        shutil.copy2(str(FIXTURE_DB), db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)

    yield db_path, conn

    conn.close()
    os.unlink(db_path)


def _seed_ingest_image(conn, *, status="INGESTED", md5="abc123", filename="test.jpg",
                       disambiguated=None, confirmed_finishes=None, claude_result=None):
    """Insert a fake ingest_images row and return its id."""
    now = "2025-01-01T00:00:00"
    conn.execute(
        """INSERT INTO ingest_images
           (filename, stored_name, md5, status, disambiguated, confirmed_finishes,
            claude_result, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (filename, filename, md5, status,
         json.dumps(disambiguated) if disambiguated else None,
         json.dumps(confirmed_finishes) if confirmed_finishes else None,
         json.dumps(claude_result) if claude_result else None,
         now, now),
    )
    image_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return image_id


def _seed_collection_entry(conn, printing_id, *, finish="nonfoil", source="ingest"):
    """Insert a fake collection entry and return its id."""
    now = "2025-01-01T00:00:00"
    conn.execute(
        """INSERT INTO collection (printing_id, finish, status, source, acquired_at)
           VALUES (?, ?, 'owned', ?, ?)""",
        (printing_id, finish, source, now),
    )
    coll_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return coll_id


def _seed_lineage(conn, collection_id, md5, card_index=0):
    """Insert a fake ingest_lineage row."""
    now = "2025-01-01T00:00:00"
    conn.execute(
        """INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at)
           VALUES (?, ?, 'uploads/test.jpg', ?, ?)""",
        (collection_id, md5, card_index, now),
    )
    conn.commit()


def _get_first_printing_id(conn):
    """Get any valid printing_id from the fixture DB."""
    row = conn.execute("SELECT printing_id FROM printings LIMIT 1").fetchone()
    return row["printing_id"] if row else "UNKNOWN"


# =============================================================================
# Reprocess tests (already uses existing _reset_ingest_image)
# =============================================================================


class TestReprocess:
    """Reprocess sends an image back through the full Agent pipeline."""

    def test_reprocess_removes_collection_entry(self, db):
        """After reprocess, the collection entry should be deleted."""
        from mtg_collector.cli.crack_pack_server import _reset_ingest_image

        db_path, conn = db
        md5 = "reprocess_test_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        removed = _reset_ingest_image(conn, image_id, md5, "2025-06-01T00:00:00")
        conn.commit()

        assert removed == 1
        # Collection entry gone
        row = conn.execute("SELECT id FROM collection WHERE id = ?", (coll_id,)).fetchone()
        assert row is None
        # Lineage gone
        row = conn.execute("SELECT id FROM ingest_lineage WHERE image_md5 = ?", (md5,)).fetchone()
        assert row is None

    def test_reprocess_resets_image_to_ready_for_ocr(self, db):
        """After reprocess, the image status should be READY_FOR_OCR with all columns nulled."""
        from mtg_collector.cli.crack_pack_server import _reset_ingest_image

        db_path, conn = db
        md5 = "reprocess_status_md5"

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=["some_printing"],
                                       confirmed_finishes=["foil"],
                                       claude_result={"cards": []})

        _reset_ingest_image(conn, image_id, md5, "2025-06-01T00:00:00")
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["status"] == "READY_FOR_OCR"
        assert img["disambiguated"] is None
        assert img["confirmed_finishes"] is None
        assert img["claude_result"] is None

    def test_reprocess_multi_card_image_removes_all(self, db):
        """Reprocessing a multi-card image removes ALL collection entries from that image."""
        from mtg_collector.cli.crack_pack_server import _reset_ingest_image

        db_path, conn = db
        md5 = "multi_card_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id, printing_id])

        coll_id_0 = _seed_collection_entry(conn, printing_id)
        coll_id_1 = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id_0, md5, card_index=0)
        _seed_lineage(conn, coll_id_1, md5, card_index=1)

        removed = _reset_ingest_image(conn, image_id, md5, "2025-06-01T00:00:00")
        conn.commit()

        assert removed == 2
        count = conn.execute(
            "SELECT COUNT(*) FROM collection WHERE id IN (?, ?)", (coll_id_0, coll_id_1)
        ).fetchone()[0]
        assert count == 0

    def test_reprocess_e2e_with_fake_agent(self, db):
        """End-to-end: reset an image, run background processing with fake agent,
        verify it ends up DONE with correct disambiguation."""
        from mtg_collector.cli.crack_pack_server import (
            _reset_ingest_image,
            _process_image_background,
        )

        db_path, conn = db
        printing_id = _get_first_printing_id(conn)

        # Copy brimstone mage image to a temp ingest dir
        ingest_dir = Path(tempfile.mkdtemp()) / "ingest_images"
        ingest_dir.mkdir()
        shutil.copy2(str(BRIMSTONE_IMAGE), str(ingest_dir / "sample_brimstone_mage.jpg"))

        # Seed ingest_cache with OCR results so OCR is skipped (agent still runs)
        ocr_fragments = [
            {"text": "Brimstone Mage", "bbox": {"x": 100, "y": 100, "w": 200, "h": 30}, "confidence": 0.99},
            {"text": "Creature - Human Shaman", "bbox": {"x": 100, "y": 140, "w": 200, "h": 30}, "confidence": 0.98},
        ]
        conn.execute(
            "INSERT INTO ingest_cache (image_md5, image_path, ocr_result, created_at) VALUES (?, ?, ?, ?)",
            (BRIMSTONE_MD5, str(ingest_dir / "sample_brimstone_mage.jpg"),
             json.dumps(ocr_fragments), "2025-01-01T00:00:00"),
        )

        # Seed image as INGESTED with a collection entry
        image_id = _seed_ingest_image(conn, md5=BRIMSTONE_MD5, status="INGESTED",
                                       filename="sample_brimstone_mage.jpg",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, BRIMSTONE_MD5, card_index=0)

        # Reset the image (reprocess step 1)
        _reset_ingest_image(conn, image_id, BRIMSTONE_MD5, "2025-06-01T00:00:00")
        conn.commit()

        # Verify reset
        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["status"] == "READY_FOR_OCR"
        assert img["disambiguated"] is None

        conn.close()

        # Run background processing with fake agent
        with mock.patch.dict(os.environ, {"MTGC_FAKE_AGENT": "1"}), \
             mock.patch("mtg_collector.cli.crack_pack_server._get_ingest_images_dir", return_value=ingest_dir):
            _process_image_background(db_path, image_id)

        # Verify the image was processed successfully
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        img = dict(conn2.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        conn2.close()

        assert img["status"] == "DONE"
        disambiguated = json.loads(img["disambiguated"])
        # Fake agent returns roe + plst, but only roe is in the test fixture DB
        assert disambiguated[0] == "1f65ebef-e159-4698-8852-650b7b6a08d3"

        # Clean up
        shutil.rmtree(ingest_dir.parent)


# =============================================================================
# Refinish tests (new endpoint)
# =============================================================================


class TestRefinish:
    """Refinish removes all collection entries for an image but preserves Agent
    identification, so the image reappears on the Recents page for finish re-selection."""

    def test_refinish_removes_collection_entry(self, db):
        """After refinish, the collection entry should be deleted."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_test_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        row = conn.execute("SELECT id FROM collection WHERE id = ?", (coll_id,)).fetchone()
        assert row is None

    def test_refinish_removes_all_lineage(self, db):
        """After refinish, all lineage rows for the image should be deleted."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_lineage_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        row = conn.execute(
            "SELECT id FROM ingest_lineage WHERE image_md5 = ?", (md5,)
        ).fetchone()
        assert row is None

    def test_refinish_preserves_agent_identification(self, db):
        """After refinish, the image's disambiguated/claude_result should be preserved."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_preserve_md5"
        printing_id = _get_first_printing_id(conn)
        claude_data = {"cards": [{"name": "Lightning Bolt"}]}

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"],
                                       claude_result=claude_data)
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["disambiguated"] is not None
        assert json.loads(img["disambiguated"]) == [printing_id]
        assert img["claude_result"] is not None

    def test_refinish_resets_image_status_to_done(self, db):
        """After refinish, the image status should be DONE (not INGESTED)."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_status_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["status"] == "DONE"

    def test_refinish_clears_all_confirmed_finishes(self, db):
        """After refinish, all confirmed_finishes entries should be null."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_finish_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id, printing_id],
                                       confirmed_finishes=["foil", "nonfoil"])
        coll_id_0 = _seed_collection_entry(conn, printing_id, finish="foil")
        coll_id_1 = _seed_collection_entry(conn, printing_id, finish="nonfoil")
        _seed_lineage(conn, coll_id_0, md5, card_index=0)
        _seed_lineage(conn, coll_id_1, md5, card_index=1)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        finishes = json.loads(img["confirmed_finishes"])
        assert finishes == [None, None]

    def test_refinish_multi_card_removes_all(self, db):
        """On a multi-card image, refinish removes ALL collection entries from that image."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_image

        db_path, conn = db
        md5 = "refinish_multi_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id, printing_id],
                                       confirmed_finishes=["nonfoil", "foil"])

        coll_id_0 = _seed_collection_entry(conn, printing_id, finish="nonfoil")
        coll_id_1 = _seed_collection_entry(conn, printing_id, finish="foil")
        _seed_lineage(conn, coll_id_0, md5, card_index=0)
        _seed_lineage(conn, coll_id_1, md5, card_index=1)

        _refinish_ingest_image(conn, image_id, md5)
        conn.commit()

        # Both removed
        count = conn.execute(
            "SELECT COUNT(*) FROM collection WHERE id IN (?, ?)", (coll_id_0, coll_id_1)
        ).fetchone()[0]
        assert count == 0

        # All lineage gone
        count = conn.execute(
            "SELECT COUNT(*) FROM ingest_lineage WHERE image_md5 = ?", (md5,)
        ).fetchone()[0]
        assert count == 0

        # Status is DONE
        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["status"] == "DONE"


# =============================================================================
# Correct page removal tests
# =============================================================================


class TestCorrectPageRemoval:
    """The /correct route should no longer exist."""

    def test_correct_html_removed(self):
        """correct.html should not exist in the static directory."""
        correct_path = Path(__file__).parent.parent / "mtg_collector" / "static" / "correct.html"
        assert not correct_path.exists(), "correct.html should be removed"

    def test_correct_route_not_in_server(self):
        """The /correct route should not be served."""
        import inspect
        from mtg_collector.cli.crack_pack_server import CrackPackHandler
        source = inspect.getsource(CrackPackHandler.do_GET)
        assert '"/correct"' not in source, "/correct route should be removed from do_GET"
