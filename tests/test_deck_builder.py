"""
Tests for the Deck Builder service.

Tests lifecycle, card management, classification, validation, audit,
plan, fill-lands, bling selection, and candidate search.

To run: uv run pytest tests/test_deck_builder.py -v
"""

import json
import math
import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.models import (
    Card,
    CardRepository,
    CollectionEntry,
    CollectionRepository,
    Deck,
    DeckRepository,
    Printing,
    PrintingRepository,
    Set,
    SetRepository,
)
from mtg_collector.db.schema import init_db
from mtg_collector.services.deck_builder.service import DeckBuilderService


def _make_raw_json(legalities=None, edhrec_rank=None):
    """Build a minimal raw_json string."""
    data = {}
    if legalities:
        data["legalities"] = legalities
    if edhrec_rank is not None:
        data["edhrec_rank"] = edhrec_rank
    return json.dumps(data)


@pytest.fixture
def db():
    """Create a fresh database with schema applied."""
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
    """Database seeded with a commander, cards, and collection entries."""
    set_repo = SetRepository(db)
    card_repo = CardRepository(db)
    printing_repo = PrintingRepository(db)
    collection_repo = CollectionRepository(db)

    # Sets
    set_repo.upsert(Set(set_code="cmd", set_name="Commander"))
    set_repo.upsert(Set(set_code="m21", set_name="Core Set 2021"))
    set_repo.upsert(Set(set_code="khm", set_name="Kaldheim"))

    # Commander: Atraxa (WUBG)
    card_repo.upsert(Card(
        oracle_id="atraxa-id",
        name="Atraxa, Praetors' Voice",
        type_line="Legendary Creature — Phyrexian Angel Horror",
        mana_cost="{G}{W}{U}{B}",
        cmc=4.0,
        oracle_text="Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
        colors=["W", "U", "B", "G"],
        color_identity=["W", "U", "B", "G"],
    ))
    printing_repo.upsert(Printing(
        printing_id="atraxa-p1", oracle_id="atraxa-id", set_code="cmd",
        collector_number="1", rarity="M",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=5),
    ))

    # Ramp card: Sol Ring
    card_repo.upsert(Card(
        oracle_id="solring-id", name="Sol Ring",
        type_line="Artifact", mana_cost="{1}", cmc=1.0,
        oracle_text="Tap: Add {C}{C}.",
        colors=[], color_identity=[],
    ))
    printing_repo.upsert(Printing(
        printing_id="solring-p1", oracle_id="solring-id", set_code="cmd",
        collector_number="2", rarity="U",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=1),
    ))

    # Removal: Swords to Plowshares
    card_repo.upsert(Card(
        oracle_id="stp-id", name="Swords to Plowshares",
        type_line="Instant", mana_cost="{W}", cmc=1.0,
        oracle_text="Exile target creature. Its controller gains life equal to its power.",
        colors=["W"], color_identity=["W"],
    ))
    printing_repo.upsert(Printing(
        printing_id="stp-p1", oracle_id="stp-id", set_code="cmd",
        collector_number="3", rarity="U",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=10),
    ))

    # Card with wrong CI (Red) — should be rejected for Atraxa
    card_repo.upsert(Card(
        oracle_id="bolt-id", name="Lightning Bolt",
        type_line="Instant", mana_cost="{R}", cmc=1.0,
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        colors=["R"], color_identity=["R"],
    ))
    printing_repo.upsert(Printing(
        printing_id="bolt-p1", oracle_id="bolt-id", set_code="m21",
        collector_number="1", rarity="U",
        raw_json=_make_raw_json({"commander": "legal"}),
    ))

    # Draw card: Rhystic Study
    card_repo.upsert(Card(
        oracle_id="rhystic-id", name="Rhystic Study",
        type_line="Enchantment", mana_cost="{2}{U}", cmc=3.0,
        oracle_text="Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
        colors=["U"], color_identity=["U"],
    ))
    printing_repo.upsert(Printing(
        printing_id="rhystic-p1", oracle_id="rhystic-id", set_code="cmd",
        collector_number="4", rarity="R",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=2),
    ))

    # Board wipe: Wrath of God
    card_repo.upsert(Card(
        oracle_id="wrath-id", name="Wrath of God",
        type_line="Sorcery", mana_cost="{2}{W}{W}", cmc=4.0,
        oracle_text="Destroy all creatures. They can't be regenerated.",
        colors=["W"], color_identity=["W"],
    ))
    printing_repo.upsert(Printing(
        printing_id="wrath-p1", oracle_id="wrath-id", set_code="cmd",
        collector_number="5", rarity="R",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=50),
    ))

    # Token maker: Avenger of Zendikar
    card_repo.upsert(Card(
        oracle_id="avenger-id", name="Avenger of Zendikar",
        type_line="Creature — Elemental", mana_cost="{5}{G}{G}", cmc=7.0,
        oracle_text="When Avenger of Zendikar enters the battlefield, create a 0/1 green Plant creature token for each land you control.",
        colors=["G"], color_identity=["G"],
    ))
    printing_repo.upsert(Printing(
        printing_id="avenger-p1", oracle_id="avenger-id", set_code="cmd",
        collector_number="6", rarity="M",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=30),
    ))

    # Reanimate card: Reanimate
    card_repo.upsert(Card(
        oracle_id="reanimate-id", name="Reanimate",
        type_line="Sorcery", mana_cost="{B}", cmc=1.0,
        oracle_text="Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to its mana value.",
        colors=["B"], color_identity=["B"],
    ))
    printing_repo.upsert(Printing(
        printing_id="reanimate-p1", oracle_id="reanimate-id", set_code="cmd",
        collector_number="7", rarity="R",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=20),
    ))

    # Utility land: Command Tower
    card_repo.upsert(Card(
        oracle_id="cmdtower-id", name="Command Tower",
        type_line="Land", mana_cost=None, cmc=0.0,
        oracle_text="{T}: Add one mana of any color in your commander's color identity.",
        colors=[], color_identity=[],
    ))
    printing_repo.upsert(Printing(
        printing_id="cmdtower-p1", oracle_id="cmdtower-id", set_code="cmd",
        collector_number="8", rarity="C",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=1),
    ))

    # Basic lands (multiple copies)
    land_cn_base = {"Plains": 200, "Island": 300, "Swamp": 400, "Forest": 500}
    for land_name, color in [("Plains", "W"), ("Island", "U"), ("Swamp", "B"), ("Forest", "G")]:
        oracle_id = f"{land_name.lower()}-id"
        card_repo.upsert(Card(
            oracle_id=oracle_id, name=land_name,
            type_line="Basic Land", mana_cost=None, cmc=0.0,
            oracle_text=None, colors=[], color_identity=[color],
        ))
        base_cn = land_cn_base[land_name]
        for i in range(10):
            pid = f"{land_name.lower()}-p{i}"
            printing_repo.upsert(Printing(
                printing_id=pid, oracle_id=oracle_id, set_code="m21",
                collector_number=f"{base_cn+i}", rarity="L",
                raw_json=_make_raw_json({"commander": "legal"}),
            ))

    # Non-legendary creature (for commander validation test)
    card_repo.upsert(Card(
        oracle_id="bear-id", name="Grizzly Bears",
        type_line="Creature — Bear", mana_cost="{1}{G}", cmc=2.0,
        oracle_text=None, colors=["G"], color_identity=["G"],
    ))
    printing_repo.upsert(Printing(
        printing_id="bear-p1", oracle_id="bear-id", set_code="m21",
        collector_number="10", rarity="C",
        raw_json=_make_raw_json({"commander": "legal"}),
    ))

    # Bling variants of Sol Ring for bling testing
    printing_repo.upsert(Printing(
        printing_id="solring-foil", oracle_id="solring-id", set_code="cmd",
        collector_number="2f", rarity="U",
        finishes=["foil"],
        raw_json=_make_raw_json({"commander": "legal"}),
    ))
    printing_repo.upsert(Printing(
        printing_id="solring-extended", oracle_id="solring-id", set_code="cmd",
        collector_number="2e", rarity="U",
        frame_effects=["extendedart"],
        raw_json=_make_raw_json({"commander": "legal"}),
    ))

    # Collection entries — owned, unassigned
    entries = {}
    for pid in ["atraxa-p1", "solring-p1", "stp-p1", "bolt-p1", "rhystic-p1",
                "wrath-p1", "bear-p1", "avenger-p1", "reanimate-p1", "cmdtower-p1"]:
        eid = collection_repo.add(CollectionEntry(id=None, printing_id=pid, finish="nonfoil"))
        entries[pid] = eid

    # Foil and extended Sol Ring copies
    entries["solring-foil"] = collection_repo.add(
        CollectionEntry(id=None, printing_id="solring-foil", finish="foil")
    )
    entries["solring-extended"] = collection_repo.add(
        CollectionEntry(id=None, printing_id="solring-extended", finish="nonfoil")
    )

    # Basic land copies
    for land_name in ["plains", "island", "swamp", "forest"]:
        for i in range(10):
            pid = f"{land_name}-p{i}"
            collection_repo.add(CollectionEntry(id=None, printing_id=pid, finish="nonfoil"))

    # Card tags
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("solring-id", "ramp"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("solring-id", "mana-rock"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("stp-id", "removal"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("stp-id", "creature-removal"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("rhystic-id", "draw"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("rhystic-id", "card-advantage"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("wrath-id", "boardwipe"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("avenger-id", "synergy-token"))
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("reanimate-id", "recursion"))

    # Salt scores
    db.execute(
        "INSERT OR IGNORE INTO salt_scores (card_name, salt_score, num_decks, fetched_at) VALUES (?, ?, ?, ?)",
        ("Rhystic Study", 3.2, 100000, "2025-01-01T00:00:00Z"),
    )

    db.commit()
    return db, entries


# =============================================================================
# Lifecycle
# =============================================================================

class TestLifecycle:
    def test_create_deck(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        result = svc.create_deck("Atraxa, Praetors' Voice")
        assert result["deck_id"] > 0
        assert result["commander"] == "Atraxa, Praetors' Voice"
        assert result["copy_assigned"] is True

    def test_create_deck_search_by_name(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        result = svc.create_deck("atraxa")
        assert result["commander"] == "Atraxa, Praetors' Voice"

    def test_create_deck_rejects_non_legendary(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        with pytest.raises(ValueError, match="not a legendary creature"):
            svc.create_deck("Grizzly Bears")

    def test_create_deck_card_not_found(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        with pytest.raises(ValueError, match="Card not found"):
            svc.create_deck("Nonexistent Card")

    def test_delete_deck(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        result = svc.create_deck("Atraxa, Praetors' Voice")
        deck_id = result["deck_id"]
        del_result = svc.delete_deck(deck_id)
        assert del_result["deck_id"] == deck_id

    def test_describe_deck(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        result = svc.create_deck("Atraxa, Praetors' Voice")
        svc.describe_deck(result["deck_id"], "Superfriends build")
        deck = DeckRepository(db).get(result["deck_id"])
        assert deck["description"] == "Superfriends build"


# =============================================================================
# Card Management
# =============================================================================

class TestCardManagement:
    def test_add_card(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.add_card(deck["deck_id"], "Sol Ring")
        assert result["card"] == "Sol Ring"
        assert result["count"] == 1

    def test_add_card_rejects_wrong_ci(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        with pytest.raises(ValueError, match="color identity"):
            svc.add_card(deck["deck_id"], "Lightning Bolt")

    def test_add_card_rejects_duplicate(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        with pytest.raises(ValueError, match="singleton"):
            svc.add_card(deck["deck_id"], "Sol Ring")

    def test_add_basic_land_allows_duplicates(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Plains", count=3)
        cards = DeckRepository(db).get_cards(deck["deck_id"])
        plains = [c for c in cards if c["name"] == "Plains"]
        assert len(plains) == 3

    def test_remove_card(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        result = svc.remove_card(deck["deck_id"], "Sol Ring")
        assert result["removed"] == 1

    def test_swap_card(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        result = svc.swap_card(deck["deck_id"], "Sol Ring", "Swords to Plowshares")
        assert result["removed"] == "Sol Ring"
        assert result["added"] == "Swords to Plowshares"

    def test_annotate_card(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        svc.annotate_card(deck["deck_id"], "Sol Ring", note="fast mana")
        cards = DeckRepository(db).get_cards(deck["deck_id"])
        sol = [c for c in cards if c["name"] == "Sol Ring"][0]
        assert sol["deck_note"] == "fast mana"

    def test_add_card_with_note(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring", note="staple")
        cards = DeckRepository(db).get_cards(deck["deck_id"])
        sol = [c for c in cards if c["name"] == "Sol Ring"][0]
        assert sol["deck_note"] == "staple"

    def test_add_card_returns_tally(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.add_card(deck["deck_id"], "Sol Ring")
        assert "tally" in result
        assert result["tally"]["total"] == 2  # commander + sol ring
        assert "categories" in result["tally"]

    def test_remove_card_returns_tally(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        result = svc.remove_card(deck["deck_id"], "Sol Ring")
        assert "tally" in result
        assert result["tally"]["total"] == 1  # just commander

    def test_add_card_explains_in_another_deck(self, seeded_db):
        """When a card is in another deck, error explains why."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck1 = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck1["deck_id"], "Rhystic Study")
        # Delete extra copies so only the deck-assigned one remains
        db.execute(
            "DELETE FROM collection WHERE printing_id = 'rhystic-p1' AND deck_id IS NULL"
        )
        db.commit()
        # Singleton rule prevents adding again to same deck, so test the error path
        # by trying from a fresh deck perspective — but singleton fires first.
        # Instead, test _explain_no_copy directly
        msg = svc._explain_no_copy("Rhystic Study", "rhystic-id")
        assert "deck" in msg.lower()

# =============================================================================
# Classification
# =============================================================================

class TestClassification:
    def test_classify_by_tag(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        # Sol Ring has "ramp" tag
        card = {"oracle_id": "solring-id", "oracle_text": "Tap: Add {C}{C}."}
        cats = svc._classify_card(card)
        assert "Ramp" in cats

    def test_classify_removal_by_tag(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        card = {"oracle_id": "stp-id", "oracle_text": "Exile target creature."}
        cats = svc._classify_card(card)
        assert "Targeted Disruption" in cats

    def test_classify_wipe_by_tag(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        card = {"oracle_id": "wrath-id", "oracle_text": "Destroy all creatures."}
        cats = svc._classify_card(card)
        assert "Mass Disruption" in cats

    def test_classify_no_tags_returns_empty(self, seeded_db):
        """Card without tags returns empty set."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        card = {"oracle_id": "no-tags-id", "oracle_text": "Search your library for a basic land card."}
        cats = svc._classify_card(card)
        assert len(cats) == 0


# =============================================================================
# Validation
# =============================================================================

class TestValidation:
    def test_check_deck_empty(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.check_deck(deck["deck_id"])
        assert result["valid"] is False
        assert any("100" in i or "need" in i for i in result["issues"])

    def test_check_commander_present(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.check_deck(deck["deck_id"])
        # Commander IS assigned, so no "No commander" issue
        assert not any("No commander" in i for i in result["issues"])


# =============================================================================
# Audit
# =============================================================================

class TestAudit:
    def test_audit_shows_gaps(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.audit_deck(deck["deck_id"])
        assert result["total"] == 1  # Just the commander
        assert len(result["gaps"]) > 0
        assert len(result["next_steps"]) > 0

    def test_audit_tracks_categories(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        result = svc.audit_deck(deck["deck_id"])
        assert result["categories"].get("Ramp", 0) >= 1

    def test_audit_returns_zero_role_cards(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Avenger has no tags in test fixture
        svc.add_card(deck["deck_id"], "Avenger of Zendikar")
        result = svc.audit_deck(deck["deck_id"])
        assert "zero_role_cards" in result
        assert "avg_roles" in result
        assert "coverage" in result

    def test_audit_returns_plan_progress(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"reanimate": 3, "tokens": 5})
        # Tag Reanimate card with "reanimate" tag
        reanimate_oid = db.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Reanimate'"
        ).fetchone()["oracle_id"]
        db.execute(
            "INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
            (reanimate_oid, "reanimate"),
        )
        svc.add_card(deck["deck_id"], "Reanimate")
        result = svc.audit_deck(deck["deck_id"])
        assert result["plan_progress"] is not None
        assert result["plan_progress"]["reanimate"]["current"] == 1
        assert result["plan_progress"]["reanimate"]["target"] == 3
        assert result["plan_progress"]["tokens"]["current"] == 0

    def test_audit_next_steps_empty_deck(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.audit_deck(deck["deck_id"])
        assert any("vision" in s.lower() or "win" in s.lower() for s in result["next_steps"])

    def test_audit_next_steps_show_gaps(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        result = svc.audit_deck(deck["deck_id"])
        # Should mention infrastructure gaps
        gap_steps = [s for s in result["next_steps"] if "need" in s]
        assert len(gap_steps) > 0


# =============================================================================
# Plan
# =============================================================================

class TestPlan:
    def test_set_and_get_plan(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"reanimate": 8, "discard": 5, "targets": 10})
        plan = svc.get_plan(deck["deck_id"])
        assert plan is not None
        assert plan["targets"] == {"reanimate": 8, "discard": 5, "targets": 10}

    def test_plan_progress_tracks_card_tags(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"reanimate": 5})
        # Tag Reanimate with "reanimate" tag
        reanimate_oid = db.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Reanimate'"
        ).fetchone()["oracle_id"]
        db.execute(
            "INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
            (reanimate_oid, "reanimate"),
        )
        svc.add_card(deck["deck_id"], "Reanimate")
        cards = svc.deck_repo.get_cards(deck["deck_id"])
        plan = svc.get_plan(deck["deck_id"])
        progress = svc._get_plan_progress(deck["deck_id"], cards, plan)
        assert progress["reanimate"]["current"] == 1
        assert progress["reanimate"]["target"] == 5

    def test_clear_plan(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 10})
        svc.clear_plan(deck["deck_id"])
        assert svc.get_plan(deck["deck_id"]) is None

    def test_no_plan_returns_none(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        assert svc.get_plan(deck["deck_id"]) is None


# =============================================================================
# Fill Lands
# =============================================================================

class TestFillLands:
    def test_fill_lands_proportional(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Add some colored cards to create pip distribution
        svc.add_card(deck["deck_id"], "Swords to Plowshares")  # W
        svc.add_card(deck["deck_id"], "Rhystic Study")  # UU
        result = svc.fill_lands(deck["deck_id"])
        assert result["added"] > 0
        assert "lands" in result
        # Should have lands distributed across colors
        assert any(count > 0 for count in result["lands"].values())

    def test_fill_lands_no_commander_errors(self, db):
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="No Commander"))
        db.commit()
        svc = DeckBuilderService(db)
        with pytest.raises(ValueError, match="No commander"):
            svc.fill_lands(deck_id)

    def test_fill_lands_returns_utility_suggestions(self, seeded_db):
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.fill_lands(deck["deck_id"])
        assert "utility_suggestions" in result
        # Command Tower should be in suggestions
        names = [s["name"] for s in result["utility_suggestions"]]
        assert "Command Tower" in names


# =============================================================================
# Bling Selection
# =============================================================================

class TestBlingSelection:
    def test_foil_preferred_over_nonfoil(self, seeded_db):
        """Foil copy should be selected over nonfoil."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.add_card(deck["deck_id"], "Sol Ring")
        # The foil or extended art copy should be picked
        cid = result["collection_ids"][0]
        # It should not be the plain nonfoil
        assert cid != entries["solring-p1"]

    def test_bling_score_calculation(self, seeded_db):
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        # Nonfoil
        assert svc._bling_score({"finish": "nonfoil", "frame_effects": None, "full_art": 0, "promo": 0, "promo_types": None}) == 0
        # Foil
        assert svc._bling_score({"finish": "foil", "frame_effects": None, "full_art": 0, "promo": 0, "promo_types": None}) == 2
        # Extended art
        assert svc._bling_score({"finish": "nonfoil", "frame_effects": '["extendedart"]', "full_art": 0, "promo": 0, "promo_types": None}) == 2


# =============================================================================
# Query
# =============================================================================

class TestQuery:
    def test_query_select(self, seeded_db):
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        rows = svc.query_db("SELECT name FROM cards LIMIT 3")
        assert len(rows) > 0
        assert "name" in rows[0]

    def test_query_rejects_non_select(self, seeded_db):
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        with pytest.raises(ValueError, match="SELECT"):
            svc.query_db("DELETE FROM cards")

    def test_query_returns_dicts(self, seeded_db):
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        rows = svc.query_db("SELECT name, cmc FROM cards WHERE name = 'Sol Ring'")
        assert len(rows) == 1
        assert rows[0]["name"] == "Sol Ring"
        assert rows[0]["cmc"] == 1.0


# =============================================================================
# Autofill
# =============================================================================

@pytest.fixture(autouse=True)
def _deterministic_autofill(monkeypatch):
    """Zero out random weight so autofill tests are deterministic."""
    from mtg_collector.services.deck_builder import service as svc_mod
    weights = {**svc_mod.AUTOFILL_WEIGHTS, "random": 0.0}
    monkeypatch.setattr(svc_mod, "AUTOFILL_WEIGHTS", weights)


class TestAutofill:
    def test_autofill_suggests_cards_for_plan(self, seeded_db):
        """Autofill should suggest cards matching plan tag targets."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 2, "draw": 1, "removal": 1})
        result = svc.autofill(deck["deck_id"])

        assert "suggestions" in result
        suggestions = result["suggestions"]

        # Sol Ring should be suggested for ramp (it has the "ramp" tag)
        assert "ramp" in suggestions
        ramp_names = [c["name"] for c in suggestions["ramp"]["cards"]]
        assert "Sol Ring" in ramp_names

        # Rhystic Study for draw
        assert "draw" in suggestions
        draw_names = [c["name"] for c in suggestions["draw"]["cards"]]
        assert "Rhystic Study" in draw_names

        # Swords to Plowshares for removal
        assert "removal" in suggestions
        removal_names = [c["name"] for c in suggestions["removal"]["cards"]]
        assert "Swords to Plowshares" in removal_names

    def test_autofill_excludes_cards_in_deck(self, seeded_db):
        """Cards already in the deck should not be suggested."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")
        svc.set_plan(deck["deck_id"], {"ramp": 2})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        if "ramp" in suggestions:
            ramp_names = [c["name"] for c in suggestions["ramp"]["cards"]]
            assert "Sol Ring" not in ramp_names

    def test_autofill_excludes_wrong_ci(self, seeded_db):
        """Cards outside commander CI should not be suggested."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        # Atraxa is WUBG — Red cards should be excluded
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("bolt-id", "removal"))
        db.commit()
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"removal": 3})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        if "removal" in suggestions:
            names = [c["name"] for c in suggestions["removal"]["cards"]]
            assert "Lightning Bolt" not in names

    def test_autofill_no_plan_raises(self, seeded_db):
        """Autofill without a plan should raise ValueError."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        with pytest.raises(ValueError, match="No plan"):
            svc.autofill(deck["deck_id"])

    def test_autofill_card_not_reused_across_tags(self, seeded_db):
        """A card suggested for one tag should not appear in another."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Sol Ring has tags: ramp, mana-rock
        svc.set_plan(deck["deck_id"], {"ramp": 1, "mana-rock": 1})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        all_oracle_ids = set()
        for tag, group in suggestions.items():
            for card in group["cards"]:
                assert card["oracle_id"] not in all_oracle_ids, \
                    f"{card['name']} suggested for multiple tags"
                all_oracle_ids.add(card["oracle_id"])

    def test_autofill_skips_met_targets(self, seeded_db):
        """Tags that are already met should not appear in suggestions."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Add Rhystic Study (has "draw" tag) then set plan target of 1 draw
        svc.add_card(deck["deck_id"], "Rhystic Study")
        svc.set_plan(deck["deck_id"], {"draw": 1})
        result = svc.autofill(deck["deck_id"])
        # draw target is met, should not appear
        assert "draw" not in result["suggestions"]

    def test_autofill_returns_scores(self, seeded_db):
        """Suggested cards should have composite scores."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 1})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        assert "ramp" in suggestions
        for card in suggestions["ramp"]["cards"]:
            assert "score" in card
            assert isinstance(card["score"], float)
            assert card["score"] >= 0

    def test_autofill_no_api_key_returns_unvalidated(self, seeded_db):
        """Autofill without API key returns unvalidated flag."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)  # no api_key
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 1})
        result = svc.autofill(deck["deck_id"])
        assert result["unvalidated"] is True

    def test_autofill_with_api_key_no_unvalidated_flag(self, seeded_db):
        """Autofill with API key does not return unvalidated flag."""
        db, entries = seeded_db
        svc = DeckBuilderService(db, api_key="test-key")
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 1})
        # Mock the validator to avoid real API calls
        from unittest.mock import patch, MagicMock
        mock_validator = MagicMock()
        mock_validator.validate_and_filter.side_effect = lambda candidates, tag, **kw: candidates
        with patch("mtg_collector.services.deck_builder.tag_validator.TagValidator", return_value=mock_validator):
            result = svc.autofill(deck["deck_id"])
        assert "unvalidated" not in result

    def test_autofill_validator_filters_invalid(self, seeded_db):
        """Validator should filter out invalid tag assignments."""
        db, entries = seeded_db
        svc = DeckBuilderService(db, api_key="test-key")
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 2})
        from unittest.mock import patch, MagicMock
        mock_validator = MagicMock()
        # Filter out all candidates (simulates all being invalid)
        mock_validator.validate_and_filter.return_value = []
        with patch("mtg_collector.services.deck_builder.tag_validator.TagValidator", return_value=mock_validator):
            result = svc.autofill(deck["deck_id"])
        # No valid candidates means no suggestions for ramp
        assert "ramp" not in result["suggestions"]


# =============================================================================
# Tag Validation
# =============================================================================

class TestTagValidation:
    def test_validate_uses_cached_results(self, seeded_db):
        """Fully-validated cards should skip Haiku call."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import TagValidator

        # Pre-populate validation cache for ALL of Sol Ring's tags (ramp + mana-rock)
        for tag in ("ramp", "mana-rock"):
            db.execute(
                "INSERT INTO card_tag_validations (oracle_id, tag, valid, reason, validated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("solring-id", tag, 1, "it ramps", "2026-01-01T00:00:00Z"),
            )
        db.commit()

        validator = TagValidator(db)
        validator.client = MagicMock()  # Should not be called

        candidates = [{"oracle_id": "solring-id", "name": "Sol Ring",
                       "type_line": "Artifact", "oracle_text": "Tap: Add {C}{C}."}]
        result = validator.validate_and_filter(candidates, "ramp")

        assert len(result) == 1
        assert result[0]["oracle_id"] == "solring-id"
        validator.client.messages.create.assert_not_called()

    def test_validate_filters_cached_invalid(self, seeded_db):
        """Cached invalid results should filter out cards."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import TagValidator

        # Pre-populate ALL tags as validated so backfill isn't triggered
        # Sol Ring has ramp + mana-rock in card_tags; add creature-removal as extra
        for tag, valid in [("ramp", 1), ("mana-rock", 1), ("creature-removal", 0)]:
            db.execute(
                "INSERT INTO card_tag_validations (oracle_id, tag, valid, reason, validated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("solring-id", tag, valid, "test", "2026-01-01T00:00:00Z"),
            )
        db.commit()

        validator = TagValidator(db)
        validator.client = MagicMock()

        candidates = [{"oracle_id": "solring-id", "name": "Sol Ring",
                       "type_line": "Artifact", "oracle_text": "Tap: Add {C}{C}."}]
        result = validator.validate_and_filter(candidates, "creature-removal")

        assert len(result) == 0
        validator.client.messages.create.assert_not_called()

    def test_validate_calls_haiku_for_unknowns(self, seeded_db):
        """Unknown cards should be sent to Haiku for all-tag validation."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import TagValidator

        validator = TagValidator(db)
        # Sol Ring has tags: ramp, mana-rock — Haiku should validate both
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text='['
            '{"name": "Sol Ring", "tag": "ramp", "valid": true, "reason": "produces mana"},'
            '{"name": "Sol Ring", "tag": "mana-rock", "valid": true, "reason": "artifact that taps for mana"}'
            ']'
        )]
        validator.client.messages.create = MagicMock(return_value=mock_response)

        candidates = [{"oracle_id": "solring-id", "name": "Sol Ring",
                       "type_line": "Artifact", "oracle_text": "Tap: Add {C}{C}."}]
        result = validator.validate_and_filter(candidates, "ramp")

        assert len(result) == 1
        validator.client.messages.create.assert_called_once()

        # Check BOTH tags were cached (all-tags validation)
        row = db.execute(
            "SELECT valid, reason FROM card_tag_validations WHERE oracle_id = ? AND tag = ?",
            ("solring-id", "ramp"),
        ).fetchone()
        assert row["valid"] == 1
        assert "produces mana" in row["reason"]

        row2 = db.execute(
            "SELECT valid, reason FROM card_tag_validations WHERE oracle_id = ? AND tag = ?",
            ("solring-id", "mana-rock"),
        ).fetchone()
        assert row2["valid"] == 1
        assert "artifact" in row2["reason"].lower()


# =============================================================================
# Scoring Improvements
# =============================================================================

class TestScoringImprovements:
    def test_log_price_compresses_outliers(self, seeded_db):
        """Log-scale price should compress the spread between cheap and expensive cards."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        # Build minimal candidates with different prices
        candidates = [
            {"name": "Cheap", "cmc": 1, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "0.25"}})},
            {"name": "Mid", "cmc": 1, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
            {"name": "Expensive", "cmc": 1, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "50.00"}})},
        ]
        scored = svc._score_candidates(candidates)

        # After log1p: cheap~0.22, mid~0.69, expensive~3.93
        # Cheap-to-mid spread should be meaningful (not vanishing)
        cheap = next(c for c in scored if c["name"] == "Cheap")
        mid = next(c for c in scored if c["name"] == "Mid")
        exp = next(c for c in scored if c["name"] == "Expensive")

        # The cheap-to-mid gap should be > 10% of total range (log compresses outliers)
        total_range = exp["_price"] - cheap["_price"]
        cheap_mid_gap = mid["_price"] - cheap["_price"]
        assert cheap_mid_gap / total_range > 0.10

    def test_novelty_log_scale(self, seeded_db):
        """Novelty should use log2(edhrec_rank) giving logarithmic separation."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        candidates = [
            {"name": "Popular", "cmc": 2, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
            {"name": "Obscure", "cmc": 2, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 10000, "prices": {"usd": "1.00"}})},
        ]
        scored = svc._score_candidates(candidates)

        popular = next(c for c in scored if c["name"] == "Popular")
        obscure = next(c for c in scored if c["name"] == "Obscure")

        # log2(100) ≈ 6.64, log2(10000) ≈ 13.29 — ratio ~2x, not 100x
        assert popular["_novelty"] == pytest.approx(math.log2(100), rel=0.01)
        assert obscure["_novelty"] == pytest.approx(math.log2(10000), rel=0.01)

    def test_score_with_per_commander_data(self, seeded_db):
        """When edhrec_data is provided, novelty should use inclusion rate."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        edhrec_data = {
            "Staple Card": 0.80,   # 80% inclusion — low novelty
            "Hidden Gem": 0.02,    # 2% inclusion — high novelty
        }
        candidates = [
            {"name": "Staple Card", "cmc": 2, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 5, "prices": {"usd": "1.00"}})},
            {"name": "Hidden Gem", "cmc": 2, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 5000, "prices": {"usd": "1.00"}})},
        ]
        scored = svc._score_candidates(candidates, edhrec_data=edhrec_data)

        staple = next(c for c in scored if c["name"] == "Staple Card")
        gem = next(c for c in scored if c["name"] == "Hidden Gem")

        # -log2(0.80) ≈ 0.32, -log2(0.02) ≈ 5.64 — gem much more novel
        assert staple["_novelty"] == pytest.approx(-math.log2(0.80), rel=0.01)
        assert gem["_novelty"] == pytest.approx(-math.log2(0.02), rel=0.01)
        assert gem["_novelty"] > staple["_novelty"]


# =============================================================================
# EDHREC Commander Cache
# =============================================================================

class TestEdhrecCommanderCache:
    def test_fetch_and_cache(self, db):
        """Should fetch from EDHREC, store in DB, and return inclusion map."""
        from unittest.mock import patch, MagicMock
        from mtg_collector.services.deck_builder.edhrec import EdhrecCommander

        client = EdhrecCommander(db)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cardlists": [
                {
                    "cardviews": [
                        {"name": "Sol Ring", "inclusion": 900, "num_decks": 1000, "synergy": 0.1},
                        {"name": "Arcane Signet", "inclusion": 800, "num_decks": 1000, "synergy": 0.2},
                    ]
                }
            ]
        }

        with patch("mtg_collector.services.deck_builder.edhrec.httpx.get", return_value=mock_response) as mock_get:
            result = client.get_inclusion_map("Atraxa, Praetors' Voice")
            mock_get.assert_called_once()

        assert result["Sol Ring"] == pytest.approx(0.9)
        assert result["Arcane Signet"] == pytest.approx(0.8)

        # Second call should use cache (no HTTP)
        with patch("mtg_collector.services.deck_builder.edhrec.httpx.get") as mock_get2:
            result2 = client.get_inclusion_map("Atraxa, Praetors' Voice")
            mock_get2.assert_not_called()

        assert result2 == result

    def test_slugify(self, db):
        from mtg_collector.services.deck_builder.edhrec import EdhrecCommander
        client = EdhrecCommander(db)
        assert client._slugify("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"
        assert client._slugify("Korvold, Fae-Cursed King") == "korvold-fae-cursed-king"

    def test_network_failure_returns_empty(self, db):
        """Network failure with no cache should return empty dict."""
        from unittest.mock import patch
        import httpx as httpx_mod
        from mtg_collector.services.deck_builder.edhrec import EdhrecCommander

        client = EdhrecCommander(db)
        with patch("mtg_collector.services.deck_builder.edhrec.httpx.get",
                    side_effect=httpx_mod.ConnectError("fail")):
            result = client.get_inclusion_map("Unknown Commander")

        assert result == {}


# =============================================================================
# Type Tags
# =============================================================================

class TestTypeTags:
    def test_parse_simple_creature(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Creature — Pirate")
        assert "type:creature" in tags
        assert "type:pirate" in tags

    def test_parse_strips_supertypes(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Legendary Creature — Human Wizard")
        assert "type:creature" in tags
        assert "type:human" in tags
        assert "type:wizard" in tags
        assert "type:legendary" not in tags

    def test_parse_artifact_creature(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Artifact Creature — Robot")
        assert "type:artifact" in tags
        assert "type:creature" in tags
        assert "type:robot" in tags

    def test_parse_no_subtypes(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Enchantment")
        assert tags == ["type:enchantment"]

    def test_parse_dfc(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Creature — Vampire // Creature — Vampire")
        assert tags.count("type:creature") == 2
        assert tags.count("type:vampire") == 2

    def test_parse_basic_land(self):
        from mtg_collector.services.deck_builder.type_tags import _parse_type_tags
        tags = _parse_type_tags("Basic Land — Forest")
        assert "type:forest" in tags
        # "Land" is not a card type we tag (not in _CARD_TYPES)
        assert "type:land" not in tags
        assert "type:basic" not in tags

    def test_insert_type_tags_into_db(self, seeded_db):
        """insert_type_tags should add type tags for all cards in the DB."""
        db, _ = seeded_db
        from mtg_collector.services.deck_builder.type_tags import insert_type_tags
        count = insert_type_tags(db)
        assert count > 0
        # Atraxa should have creature and subtypes
        tags = [r[0] for r in db.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = 'atraxa-id' AND tag LIKE 'type:%'"
        ).fetchall()]
        assert "type:creature" in tags
        assert "type:angel" in tags


