"""
Tests for ID-based card ingestion (ingest-ids / resolve_and_add_ids).

Tests the local DB lookup + collection insertion pipeline.
Does NOT use Claude — only local SQLite (pre-populated test fixture).

Test categories:
  1. Valid quads: cards resolve and get added correctly
  2. Foil handling: foil flag propagates to collection entry
  3. Invalid inputs: bad rarity, bad set, bad CN — fail cleanly
  4. CLI argument parsing: --id validation

To run: pytest tests/test_ingest_ids.py -v
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from mtg_collector.db import (
    get_connection,
    init_db,
    CardRepository,
    SetRepository,
    PrintingRepository,
    CollectionRepository,
)
from mtg_collector.db.connection import close_connection
from mtg_collector.cli.ingest_ids import resolve_and_add_ids, RARITY_MAP
from mtg_collector.utils import normalize_condition

# Pre-populated test fixture with card data (no network needed)
FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"

# Test cards from FDN set (present in fixture)
# FDN 150 = Aegis Turtle (common)
# FDN 488 = Adamant Will (common)
# FDN 3   = Armasaur Guide (common)
# FDN 2   = Arahbo, the First Fang (rare)
# FDN 4   = Cat Collector (uncommon)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_db():
    """Create a temporary database from the pre-built test fixture."""
    close_connection()
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name

    shutil.copy2(str(FIXTURE_DB), db_path)
    conn = get_connection(db_path)
    init_db(conn)  # Apply any pending migrations

    yield db_path, conn

    close_connection()
    os.unlink(db_path)


@pytest.fixture
def repos(test_db):
    """Create all repositories from a test DB connection."""
    db_path, conn = test_db
    return {
        "conn": conn,
        "db_path": db_path,
        "card_repo": CardRepository(conn),
        "set_repo": SetRepository(conn),
        "printing_repo": PrintingRepository(conn),
        "collection_repo": CollectionRepository(conn),
    }


# =============================================================================
# Valid ingestion tests
# =============================================================================

class TestValidIngestion:
    """Test that valid quads resolve and get added to the collection."""

    def test_single_card(self, repos):
        """A single valid quad should add one card."""
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "150",
            "set_code": "fdn",
            "foil": False,
        }]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint",
            source="test",
        )

        assert added == 1
        assert failed == []

        # Verify it's in the collection
        collection = repos["collection_repo"].list_all()
        assert len(collection) == 1
        assert collection[0]["name"] == "Aegis Turtle"
        assert collection[0]["finish"] == "nonfoil"

    def test_multiple_cards(self, repos):
        """Multiple valid quads should all be added."""
        entries = [
            {"rarity_code": "C", "rarity": "common", "collector_number": "150", "set_code": "fdn", "foil": False},
            {"rarity_code": "R", "rarity": "rare", "collector_number": "2", "set_code": "fdn", "foil": False},
            {"rarity_code": "U", "rarity": "uncommon", "collector_number": "4", "set_code": "fdn", "foil": False},
        ]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint",
            source="test",
        )

        assert added == 3
        assert failed == []

        collection = repos["collection_repo"].list_all()
        names = sorted(e["name"] for e in collection)
        assert len(names) == 3
        assert "Aegis Turtle" in names
        assert "Arahbo, the First Fang" in names
        assert "Cat Collector" in names

    def test_source_image_stored(self, repos):
        """source_image should be stored and retrievable from collection entries."""
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "150",
            "set_code": "fdn",
            "foil": False,
        }]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint",
            source="test",
            source_image="/photos/test.jpg",
        )

        assert added == 1

        # Verify source_image is stored
        entry = repos["collection_repo"].get(1)
        assert entry.source_image == "/photos/test.jpg"

    def test_leading_zeros_stripped(self, repos):
        """Collector numbers with leading zeros should still resolve."""
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "0003",
            "set_code": "fdn",
            "foil": False,
        }]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint",
            source="test",
        )

        assert added == 1
        assert failed == []


# =============================================================================
# Foil handling tests
# =============================================================================

class TestFoilHandling:
    """Test that foil flag propagates correctly."""

    def test_nonfoil_card(self, repos):
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "150",
            "set_code": "fdn",
            "foil": False,
        }]

        resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint", source="test",
        )

        collection = repos["collection_repo"].list_all()
        assert collection[0]["finish"] == "nonfoil"

    def test_foil_card(self, repos):
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "150",
            "set_code": "fdn",
            "foil": True,
        }]

        resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint", source="test",
        )

        collection = repos["collection_repo"].list_all()
        assert collection[0]["finish"] == "foil"


# =============================================================================
# Failure / edge case tests
# =============================================================================

class TestInvalidInputs:
    """Test that invalid inputs fail cleanly without adding any cards."""

    def test_invalid_collector_number(self, repos):
        """A non-existent collector number should fail."""
        entries = [{
            "rarity_code": "C",
            "rarity": "common",
            "collector_number": "9999",
            "set_code": "fdn",
            "foil": False,
        }]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint", source="test",
        )

        assert added == 0
        assert len(failed) == 1
        assert repos["collection_repo"].count() == 0

    def test_mixed_valid_and_invalid(self, repos):
        """If one card fails, the failure is reported but valid cards still count."""
        entries = [
            {"rarity_code": "C", "rarity": "common", "collector_number": "150", "set_code": "fdn", "foil": False},
            {"rarity_code": "C", "rarity": "common", "collector_number": "9999", "set_code": "fdn", "foil": False},
        ]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint", source="test",
        )

        # resolve_and_add_ids adds valid ones and reports failures;
        # the caller (CLI) decides whether to commit or rollback
        assert added == 1
        assert len(failed) == 1

    def test_rarity_mismatch_still_adds(self, repos):
        """Wrong rarity code should warn but still add the card."""
        # Card 150 in FDN is common, but we say it's rare
        entries = [{
            "rarity_code": "R",
            "rarity": "rare",
            "collector_number": "150",
            "set_code": "fdn",
            "foil": False,
        }]

        added, failed = resolve_and_add_ids(
            entries=entries,
            printing_repo=repos["printing_repo"],
            collection_repo=repos["collection_repo"],
            condition="Near Mint", source="test",
        )

        assert added == 1
        assert failed == []


# =============================================================================
# CLI argument parsing tests (via subprocess)
# =============================================================================

class TestCLIParsing:
    """Test CLI argument validation (no DB needed)."""

    def test_too_few_id_fields(self, test_db):
        """--id with fewer than 3 values should exit with error."""
        import subprocess
        import sys

        db_path, conn = test_db
        close_connection()

        result = subprocess.run(
            [sys.executable, "-m", "mtg_collector", "--db", db_path,
             "ingest-ids", "--id", "C", "0187"],
            capture_output=True, text=True,
        )

        assert result.returncode != 0
        assert "3 or 4 values" in result.stdout or "Error" in result.stdout

    def test_too_many_id_fields(self, test_db):
        """--id with more than 4 values should exit with error."""
        import subprocess
        import sys

        db_path, conn = test_db
        close_connection()

        result = subprocess.run(
            [sys.executable, "-m", "mtg_collector", "--db", db_path,
             "ingest-ids", "--id", "C", "0187", "EOE", "foil", "extra"],
            capture_output=True, text=True,
        )

        assert result.returncode != 0
        assert "3 or 4 values" in result.stdout or "Error" in result.stdout

    def test_invalid_rarity_code(self, test_db):
        """--id with invalid rarity letter should exit with error."""
        import subprocess
        import sys

        db_path, conn = test_db
        close_connection()

        result = subprocess.run(
            [sys.executable, "-m", "mtg_collector", "--db", db_path,
             "ingest-ids", "--id", "X", "0187", "EOE"],
            capture_output=True, text=True,
        )

        assert result.returncode != 0
        assert "Invalid rarity" in result.stdout

    def test_missing_required_id(self, test_db):
        """ingest-ids without any --id should fail."""
        import subprocess
        import sys

        db_path, conn = test_db
        close_connection()

        result = subprocess.run(
            [sys.executable, "-m", "mtg_collector", "--db", db_path,
             "ingest-ids"],
            capture_output=True, text=True,
        )

        assert result.returncode != 0
