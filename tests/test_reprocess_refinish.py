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

import pytest

from mtg_collector.db.schema import init_db

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"


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


# =============================================================================
# Refinish tests (new endpoint)
# =============================================================================


class TestRefinish:
    """Refinish removes the collection entry but preserves Agent identification,
    so the card reappears on the Recents page for finish re-selection."""

    def test_refinish_removes_collection_entry(self, db):
        """After refinish, the specific collection entry should be deleted."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_test_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        conn.commit()

        # Collection entry should be gone
        row = conn.execute("SELECT id FROM collection WHERE id = ?", (coll_id,)).fetchone()
        assert row is None

    def test_refinish_removes_lineage_for_card_index(self, db):
        """After refinish, the lineage row for the specific card_index should be deleted."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_lineage_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        conn.commit()

        row = conn.execute(
            "SELECT id FROM ingest_lineage WHERE image_md5 = ? AND card_index = ?",
            (md5, 0),
        ).fetchone()
        assert row is None

    def test_refinish_preserves_agent_identification(self, db):
        """After refinish, the image's disambiguated/claude_result should be preserved."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

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

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        # Agent identification preserved
        assert img["disambiguated"] is not None
        assert json.loads(img["disambiguated"]) == [printing_id]
        assert img["claude_result"] is not None

    def test_refinish_resets_image_status_to_done(self, db):
        """After refinish, the image status should be DONE (not INGESTED)."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_status_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["nonfoil"])
        coll_id = _seed_collection_entry(conn, printing_id)
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        assert img["status"] == "DONE"

    def test_refinish_clears_confirmed_finish_for_card(self, db):
        """After refinish, the confirmed_finishes entry for this card_index should be null."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_finish_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id],
                                       confirmed_finishes=["foil"])
        coll_id = _seed_collection_entry(conn, printing_id, finish="foil")
        _seed_lineage(conn, coll_id, md5, card_index=0)

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        finishes = json.loads(img["confirmed_finishes"])
        assert finishes[0] is None

    def test_refinish_multi_card_only_removes_target(self, db):
        """On a multi-card image, refinish only removes the targeted card's collection entry."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

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

        # Refinish only card_index=1
        _refinish_ingest_card(conn, image_id, md5, card_index=1)
        conn.commit()

        # Card 0 still exists
        row = conn.execute("SELECT id FROM collection WHERE id = ?", (coll_id_0,)).fetchone()
        assert row is not None
        # Card 1 removed
        row = conn.execute("SELECT id FROM collection WHERE id = ?", (coll_id_1,)).fetchone()
        assert row is None

    def test_refinish_multi_card_keeps_ingested_if_others_remain(self, db):
        """If other cards from the image are still ingested, status stays INGESTED."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_partial_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id, printing_id],
                                       confirmed_finishes=["nonfoil", "foil"])

        coll_id_0 = _seed_collection_entry(conn, printing_id, finish="nonfoil")
        coll_id_1 = _seed_collection_entry(conn, printing_id, finish="foil")
        _seed_lineage(conn, coll_id_0, md5, card_index=0)
        _seed_lineage(conn, coll_id_1, md5, card_index=1)

        # Refinish only card 1 — card 0 still has lineage
        _refinish_ingest_card(conn, image_id, md5, card_index=1)
        conn.commit()

        img = dict(conn.execute("SELECT * FROM ingest_images WHERE id = ?", (image_id,)).fetchone())
        # Still INGESTED because card 0 is still in collection
        assert img["status"] == "INGESTED"

    def test_refinish_multi_card_goes_done_when_all_refinished(self, db):
        """When all cards from an image are refinished, status goes to DONE."""
        from mtg_collector.cli.crack_pack_server import _refinish_ingest_card

        db_path, conn = db
        md5 = "refinish_all_md5"
        printing_id = _get_first_printing_id(conn)

        image_id = _seed_ingest_image(conn, md5=md5, status="INGESTED",
                                       disambiguated=[printing_id, printing_id],
                                       confirmed_finishes=["nonfoil", "foil"])

        coll_id_0 = _seed_collection_entry(conn, printing_id, finish="nonfoil")
        coll_id_1 = _seed_collection_entry(conn, printing_id, finish="foil")
        _seed_lineage(conn, coll_id_0, md5, card_index=0)
        _seed_lineage(conn, coll_id_1, md5, card_index=1)

        _refinish_ingest_card(conn, image_id, md5, card_index=0)
        _refinish_ingest_card(conn, image_id, md5, card_index=1)
        conn.commit()

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
