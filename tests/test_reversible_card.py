"""Tests for reversible_card layout handling in cache import.

Reversible cards (e.g. ECL shocklands) have oracle_id on card_faces
instead of at the top level. The cache import must pull oracle_id from
card_faces[0] when it's missing at the top level.

To run: uv run pytest tests/test_reversible_card.py -v
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mtg_collector.db import (
    CardRepository,
    PrintingRepository,
    SetRepository,
    get_connection,
    init_db,
)
from mtg_collector.services.bulk_import import ScryfallBulkClient, ensure_set_populated, resolve_reversible_oracle_id


# -- Fixtures: synthetic reversible_card data matching Scryfall's shape --

REVERSIBLE_ORACLE_ID = "f1750962-a87c-49f6-b731-02ae971ac6ea"

REVERSIBLE_CARD_DATA = {
    "id": "19cba6be-7291-4788-9241-87dad3b68363",
    "name": "Hallowed Fountain // Hallowed Fountain",
    "layout": "reversible_card",
    "set": "ecl",
    "collector_number": "347",
    "lang": "en",
    "cmc": 0.0,
    "type_line": "Land — Plains Island",
    "colors": [],
    "color_identity": ["U", "W"],
    "rarity": "rare",
    "finishes": ["nonfoil", "foil"],
    "card_faces": [
        {
            "oracle_id": REVERSIBLE_ORACLE_ID,
            "name": "Hallowed Fountain",
            "mana_cost": "",
            "type_line": "Land — Plains Island",
            "oracle_text": "({T}: Add {W} or {U}.)\nAs Hallowed Fountain enters, you may pay 2 life. If you don't, it enters tapped.",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/1/9/19cba6be.jpg",
                "normal": "https://cards.scryfall.io/normal/front/1/9/19cba6be.jpg",
            },
        },
        {
            "oracle_id": REVERSIBLE_ORACLE_ID,
            "name": "Hallowed Fountain",
            "mana_cost": "",
            "type_line": "Land — Plains Island",
            "oracle_text": "({T}: Add {W} or {U}.)\nAs Hallowed Fountain enters, you may pay 2 life. If you don't, it enters tapped.",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/back/1/9/19cba6be.jpg",
                "normal": "https://cards.scryfall.io/normal/back/1/9/19cba6be.jpg",
            },
        },
    ],
}

# A normal card for comparison
NORMAL_CARD_DATA = {
    "oracle_id": "aaaa-bbbb-cccc-dddd",
    "id": "normal-card-id-1234",
    "name": "Lightning Bolt",
    "layout": "normal",
    "set": "ecl",
    "collector_number": "100",
    "lang": "en",
    "cmc": 1.0,
    "type_line": "Instant",
    "mana_cost": "{R}",
    "colors": ["R"],
    "color_identity": ["R"],
    "rarity": "common",
    "finishes": ["nonfoil"],
    "image_uris": {
        "small": "https://cards.scryfall.io/small/front/bolt.jpg",
        "normal": "https://cards.scryfall.io/normal/front/bolt.jpg",
    },
}


# Reversible card with NULL top-level metadata (matches real SLD 1458 structure)
REVERSIBLE_NULL_METADATA = {
    "id": "sld-death-baron-reversible",
    "name": "Death Baron // Death Baron",
    "layout": "reversible_card",
    "set": "sld",
    "collector_number": "1458",
    "lang": "en",
    "cmc": None,
    "type_line": None,
    "oracle_text": None,
    "mana_cost": None,
    "colors": None,
    "color_identity": ["B"],
    "rarity": "rare",
    "finishes": ["nonfoil", "foil"],
    "card_faces": [
        {
            "oracle_id": "99024aa8-5687-4d38-8a4b-feef42d6c1ff",
            "name": "Death Baron",
            "mana_cost": "{1}{B}{B}",
            "type_line": "Creature \u2014 Zombie Wizard",
            "oracle_text": "Skeletons you control and other Zombies you control get +1/+1 and have deathtouch.",
            "colors": ["B"],
            "cmc": 3.0,
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/sld/1458.jpg",
                "normal": "https://cards.scryfall.io/normal/front/sld/1458.jpg",
            },
        },
        {
            "oracle_id": "99024aa8-5687-4d38-8a4b-feef42d6c1ff",
            "name": "Death Baron",
            "mana_cost": "{1}{B}{B}",
            "type_line": "Creature \u2014 Zombie Wizard",
            "oracle_text": "Skeletons you control and other Zombies you control get +1/+1 and have deathtouch.",
            "colors": ["B"],
            "cmc": 3.0,
            "image_uris": {
                "small": "https://cards.scryfall.io/small/back/sld/1458.jpg",
                "normal": "https://cards.scryfall.io/normal/back/sld/1458.jpg",
            },
        },
    ],
}

# The normal printing of the same card
NORMAL_DEATH_BARON = {
    "oracle_id": "99024aa8-5687-4d38-8a4b-feef42d6c1ff",
    "id": "m19-death-baron",
    "name": "Death Baron",
    "layout": "normal",
    "set": "m19",
    "collector_number": "90",
    "lang": "en",
    "cmc": 3.0,
    "type_line": "Creature \u2014 Zombie Wizard",
    "mana_cost": "{1}{B}{B}",
    "oracle_text": "Skeletons you control and other Zombies you control get +1/+1 and have deathtouch.",
    "colors": ["B"],
    "color_identity": ["B"],
    "rarity": "rare",
    "finishes": ["nonfoil", "foil"],
    "image_uris": {
        "small": "https://cards.scryfall.io/small/front/m19/90.jpg",
        "normal": "https://cards.scryfall.io/normal/front/m19/90.jpg",
    },
}


@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    conn = get_connection(tmp.name)
    init_db(conn)
    # Insert the ECL set
    conn.execute(
        "INSERT INTO sets (set_code, set_name, set_type, released_at) VALUES (?, ?, ?, ?)",
        ("ecl", "Lorwyn Eclipsed", "expansion", "2025-09-01"),
    )
    conn.commit()
    yield conn
    conn.close()
    Path(tmp.name).unlink(missing_ok=True)


class TestReversibleCardBulkImport:
    """Test that reversible_card layout cards are imported by cache_all's main loop."""

    def test_resolve_oracle_id_from_faces(self):
        """resolve_reversible_oracle_id should promote oracle_id from card_faces[0]."""
        from mtg_collector.services.bulk_import import resolve_reversible_oracle_id

        card_data = dict(REVERSIBLE_CARD_DATA)
        assert "oracle_id" not in card_data

        resolved = resolve_reversible_oracle_id(card_data)
        assert resolved is True
        assert card_data["oracle_id"] == REVERSIBLE_ORACLE_ID

    def test_resolve_oracle_id_noop_for_normal_cards(self):
        """resolve_reversible_oracle_id is a no-op when oracle_id already present."""
        from mtg_collector.services.bulk_import import resolve_reversible_oracle_id

        card_data = dict(NORMAL_CARD_DATA)
        resolved = resolve_reversible_oracle_id(card_data)
        assert resolved is False
        assert card_data["oracle_id"] == "aaaa-bbbb-cccc-dddd"

    def test_resolve_returns_false_without_faces(self):
        """resolve_reversible_oracle_id returns False for cards with no oracle_id and no faces."""
        from mtg_collector.services.bulk_import import resolve_reversible_oracle_id

        card_data = {"id": "no-oracle", "name": "Token", "set": "ecl"}
        resolved = resolve_reversible_oracle_id(card_data)
        assert resolved is False
        assert "oracle_id" not in card_data

    def test_to_card_model_works_after_resolution(self):
        """to_card_model succeeds on reversible_card data after oracle_id resolution."""
        from mtg_collector.services.bulk_import import resolve_reversible_oracle_id

        api = ScryfallBulkClient()
        card_data = dict(REVERSIBLE_CARD_DATA)
        resolve_reversible_oracle_id(card_data)

        card = api.to_card_model(card_data)
        assert card.oracle_id == REVERSIBLE_ORACLE_ID

    def test_to_printing_model_works_after_resolution(self):
        """to_printing_model succeeds on reversible_card data after oracle_id resolution."""
        from mtg_collector.services.bulk_import import resolve_reversible_oracle_id

        api = ScryfallBulkClient()
        card_data = dict(REVERSIBLE_CARD_DATA)
        resolve_reversible_oracle_id(card_data)

        printing = api.to_printing_model(card_data)
        assert printing.oracle_id == REVERSIBLE_ORACLE_ID
        assert printing.set_code == "ecl"
        assert printing.collector_number == "347"

    def test_normal_card_unaffected(self):
        """Normal cards with top-level oracle_id should work as before."""
        api = ScryfallBulkClient()
        card = api.to_card_model(NORMAL_CARD_DATA)
        assert card.oracle_id == "aaaa-bbbb-cccc-dddd"

        printing = api.to_printing_model(NORMAL_CARD_DATA)
        assert printing.oracle_id == "aaaa-bbbb-cccc-dddd"


class TestReversibleNullMetadata:
    """Test that reversible cards with NULL top-level metadata extract fields from faces."""

    def test_reversible_card_extracts_name_from_face(self):
        """Reversible card with '// ' in name should use face[0] name."""
        api = ScryfallBulkClient()
        card_data = dict(REVERSIBLE_NULL_METADATA)
        resolve_reversible_oracle_id(card_data)
        card = api.to_card_model(card_data)
        assert card.name == "Death Baron"

    def test_reversible_card_extracts_all_metadata_from_face(self):
        """All NULL top-level fields should fall back to face[0]."""
        api = ScryfallBulkClient()
        card_data = dict(REVERSIBLE_NULL_METADATA)
        resolve_reversible_oracle_id(card_data)
        card = api.to_card_model(card_data)
        assert card.type_line == "Creature \u2014 Zombie Wizard"
        assert card.cmc == 3.0
        assert card.colors == ["B"]
        assert "deathtouch" in card.oracle_text

    def test_reversible_upsert_does_not_corrupt_existing_card(self, db):
        """Upserting a reversible printing after a normal one must not corrupt the card row."""
        api = ScryfallBulkClient()
        card_repo = CardRepository(db)

        # First: insert from normal printing
        normal_card = api.to_card_model(NORMAL_DEATH_BARON)
        card_repo.upsert(normal_card)
        card = card_repo.get(normal_card.oracle_id)
        assert card.name == "Death Baron"

        # Second: upsert from reversible printing (would corrupt before fix)
        rev_data = dict(REVERSIBLE_NULL_METADATA)
        resolve_reversible_oracle_id(rev_data)
        rev_card = api.to_card_model(rev_data)
        card_repo.upsert(rev_card)

        card = card_repo.get(rev_card.oracle_id)
        assert card.name == "Death Baron"
        assert card.type_line == "Creature \u2014 Zombie Wizard"
        assert card.cmc == 3.0

    def test_reversible_first_then_normal_also_correct(self, db):
        """Order shouldn't matter — reversible first, normal second, still correct."""
        api = ScryfallBulkClient()
        card_repo = CardRepository(db)

        # Reversible first
        rev_data = dict(REVERSIBLE_NULL_METADATA)
        resolve_reversible_oracle_id(rev_data)
        card_repo.upsert(api.to_card_model(rev_data))

        # Normal second
        card_repo.upsert(api.to_card_model(NORMAL_DEATH_BARON))

        card = card_repo.get("99024aa8-5687-4d38-8a4b-feef42d6c1ff")
        assert card.name == "Death Baron"
        assert card.type_line == "Creature \u2014 Zombie Wizard"


class TestReversibleCardEnsureSetPopulated:
    """Test that ensure_set_populated handles reversible cards."""

    def test_ensure_set_populated_imports_reversible_cards(self, db):
        """ensure_set_populated should import reversible cards, not skip them."""
        api = ScryfallBulkClient()
        card_repo = CardRepository(db)
        set_repo = SetRepository(db)
        printing_repo = PrintingRepository(db)

        # Mock the API to return our test data
        api.get_set_cards = MagicMock(return_value=[
            NORMAL_CARD_DATA,
            REVERSIBLE_CARD_DATA,
        ])
        api.get_set = MagicMock(return_value={
            "code": "ecl",
            "name": "Lorwyn Eclipsed",
            "set_type": "expansion",
            "released_at": "2025-09-01",
        })

        result = ensure_set_populated(api, "ecl", card_repo, set_repo, printing_repo, db)
        assert result is True

        # Both cards should be in the database
        normal_printing = printing_repo.get_by_set_cn("ecl", "100")
        assert normal_printing is not None, "Normal card should be imported"

        reversible_printing = printing_repo.get_by_set_cn("ecl", "347")
        assert reversible_printing is not None, "Reversible card should be imported"
        assert reversible_printing.oracle_id == REVERSIBLE_ORACLE_ID
