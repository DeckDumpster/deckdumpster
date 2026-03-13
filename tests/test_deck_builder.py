"""
Tests for the Deck Builder service.

Tests lifecycle, card management, classification, validation, audit,
plan, fill-lands, bling selection, and candidate search.

To run: uv run pytest tests/test_deck_builder.py -v
"""

import json
import math
import os
import random
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


def _make_raw_json(legalities=None, edhrec_rank=None, produced_mana=None):
    """Build a minimal raw_json string."""
    data = {}
    if legalities:
        data["legalities"] = legalities
    if edhrec_rank is not None:
        data["edhrec_rank"] = edhrec_rank
    if produced_mana is not None:
        data["produced_mana"] = produced_mana
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

    # Shock land: Breeding Pool (U/G, enters tapped unless you pay 2 life)
    card_repo.upsert(Card(
        oracle_id="breedingpool-id", name="Breeding Pool",
        type_line="Land — Forest Island", mana_cost=None, cmc=0.0,
        oracle_text="({T}: Add {G} or {U}.)\nAs Breeding Pool enters the battlefield, you may pay 2 life. If you don't, it enters the battlefield tapped.",
        colors=[], color_identity=["G", "U"],
    ))
    printing_repo.upsert(Printing(
        printing_id="breedingpool-p1", oracle_id="breedingpool-id", set_code="cmd",
        collector_number="9", rarity="R",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=100, produced_mana=["G", "U"]),
    ))

    # Tapland: Simic Guildgate (U/G, always enters tapped)
    card_repo.upsert(Card(
        oracle_id="simicgate-id", name="Simic Guildgate",
        type_line="Land — Gate", mana_cost=None, cmc=0.0,
        oracle_text="Simic Guildgate enters the battlefield tapped.\n{T}: Add {G} or {U}.",
        colors=[], color_identity=["G", "U"],
    ))
    printing_repo.upsert(Printing(
        printing_id="simicgate-p1", oracle_id="simicgate-id", set_code="cmd",
        collector_number="10a", rarity="C",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=5000, produced_mana=["G", "U"]),
    ))

    # Fetch land: Evolving Wilds (any color via search, null produced_mana)
    card_repo.upsert(Card(
        oracle_id="evolvingwilds-id", name="Evolving Wilds",
        type_line="Land", mana_cost=None, cmc=0.0,
        oracle_text="{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
        colors=[], color_identity=[],
    ))
    printing_repo.upsert(Printing(
        printing_id="evolvingwilds-p1", oracle_id="evolvingwilds-id", set_code="cmd",
        collector_number="11", rarity="C",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=200),
    ))

    # Off-CI land: Boros Garrison (R/W — should be excluded for Atraxa since R not in CI)
    card_repo.upsert(Card(
        oracle_id="borosgarrison-id", name="Boros Garrison",
        type_line="Land", mana_cost=None, cmc=0.0,
        oracle_text="Boros Garrison enters the battlefield tapped.\nWhen Boros Garrison enters the battlefield, return a land you control to its owner's hand.\n{T}: Add {R}{W}.",
        colors=[], color_identity=["R", "W"],
    ))
    printing_repo.upsert(Printing(
        printing_id="borosgarrison-p1", oracle_id="borosgarrison-id", set_code="cmd",
        collector_number="12", rarity="C",
        raw_json=_make_raw_json({"commander": "legal"}, edhrec_rank=3000, produced_mana=["R", "W"]),
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
                "wrath-p1", "bear-p1", "avenger-p1", "reanimate-p1", "cmdtower-p1",
                "breedingpool-p1", "simicgate-p1", "evolvingwilds-p1", "borosgarrison-p1"]:
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

    # Spider Token (should be excluded by autofill)
    card_repo.upsert(Card(
        oracle_id="spider-token-id", name="Spider",
        type_line="Token Creature — Spider", mana_cost=None, cmc=0.0,
        oracle_text="Reach", colors=["G"], color_identity=["G"],
    ))
    printing_repo.upsert(Printing(
        printing_id="spider-token-p1", oracle_id="spider-token-id", set_code="cmd",
        collector_number="T1", rarity="T",
        raw_json=_make_raw_json({"commander": "legal"}),
    ))
    entries["spider-token-p1"] = collection_repo.add(
        CollectionEntry(id=None, printing_id="spider-token-p1", finish="nonfoil")
    )

    # Card tags
    db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)", ("spider-token-id", "type:spider"))
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
        assert plan["targets"]["reanimate"]["count"] == 8
        assert plan["targets"]["discard"]["count"] == 5
        assert plan["targets"]["targets"]["count"] == 10
        assert plan["targets"]["reanimate"]["type"] == "tag"

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

    def test_edit_plan_replaces_targets(self, seeded_db):
        """Editing a plan replaces targets entirely — rename, add, remove."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 10, "draw": 8, "boardwipe": 5})
        # Edit: rename draw→card-advantage, remove boardwipe, add evasion
        svc.set_plan(deck["deck_id"], {"ramp": 12, "card-advantage": 8, "evasion": 4})
        plan = svc.get_plan(deck["deck_id"])
        assert plan["targets"]["ramp"]["count"] == 12
        assert plan["targets"]["card-advantage"]["count"] == 8
        assert plan["targets"]["evasion"]["count"] == 4
        assert "draw" not in plan["targets"]
        assert "boardwipe" not in plan["targets"]

    def test_invalidated_tags_excluded_from_deck_cards(self, seeded_db):
        """Tags validated as invalid must not appear in deck card tags."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Sol Ring")

        sol_oid = db.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Sol Ring'"
        ).fetchone()["oracle_id"]

        # Give Sol Ring two tags
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   (sol_oid, "ramp"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   (sol_oid, "boardwipe"))
        # Invalidate boardwipe
        db.execute(
            "INSERT OR REPLACE INTO card_tag_validations "
            "(oracle_id, tag, valid, reason, validated_at) VALUES (?, ?, ?, ?, ?)",
            (sol_oid, "boardwipe", 0, "Not a boardwipe", "2024-01-01T00:00:00Z"),
        )
        db.commit()

        cards = svc.deck_repo.get_cards(deck["deck_id"])
        sol = [c for c in cards if c["name"] == "Sol Ring"][0]
        tags = sol["tags"].split(",") if sol["tags"] else []
        assert "ramp" in tags
        assert "boardwipe" not in tags

    def test_keyword_tags_prevalidated(self, seeded_db):
        """Keyword-derived tags get pre-validated so Haiku can't override them."""
        from mtg_collector.services.deck_builder.tags import _apply_keyword_tags

        db, entries = seeded_db
        # Pick a card with a keyword — Sol Ring has no keywords, use one that does
        # Insert a fake card with flying
        db.execute(
            "INSERT OR IGNORE INTO cards (oracle_id, name, oracle_text, colors, cmc) "
            "VALUES ('fake-flyer', 'Test Bird', 'Flying', '[]', 1)"
        )
        db.commit()

        tag_cards: dict[str, set] = {}
        _apply_keyword_tags(db, tag_cards, {"fake-flyer"})

        assert "fake-flyer" in tag_cards.get("evasion", set())

        # Check that a validation record was written
        row = db.execute(
            "SELECT valid, reason FROM card_tag_validations "
            "WHERE oracle_id = 'fake-flyer' AND tag = 'evasion'"
        ).fetchone()
        assert row is not None
        assert row["valid"] == 1
        assert row["reason"] == "keyword_match"


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
        """fill_lands backward compat — auto-adds nonbasic + basic lands."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        result = svc.fill_lands(deck["deck_id"])
        assert result["added"] > 0
        assert "lands" in result


# =============================================================================
# Land Suggestions
# =============================================================================

class TestSuggestLands:
    def test_suggest_lands_returns_nonbasics_and_basics(self, seeded_db):
        """suggest_lands should return both nonbasic and basic land suggestions."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        result = svc.suggest_lands(deck["deck_id"])
        assert result["deck_id"] == deck["deck_id"]
        assert result["land_target"] > 0
        assert "nonbasic" in result["suggestions"]
        assert "basic" in result["suggestions"]
        # Should have some nonbasic suggestions
        nonbasic_names = [s["name"] for s in result["suggestions"]["nonbasic"]]
        assert len(nonbasic_names) > 0
        # Should have basic land suggestions
        assert len(result["suggestions"]["basic"]) > 0
        # Each nonbasic should have required fields
        for land in result["suggestions"]["nonbasic"]:
            assert "collection_id" in land
            assert "score" in land
            assert "produced_mana" in land
            assert "enters_tapped" in land

    def test_suggest_lands_untapped_preferred(self, seeded_db):
        """Shock land (conditionally untapped) should score higher than tapland."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        # Seed the random for deterministic test
        random.seed(42)
        result = svc.suggest_lands(deck["deck_id"])
        nonbasic = result["suggestions"]["nonbasic"]
        names = [s["name"] for s in nonbasic]
        # Both should be present
        assert "Breeding Pool" in names
        assert "Simic Guildgate" in names
        # Breeding Pool should score higher (better EDHREC + untapped bonus)
        bp_score = next(s["score"] for s in nonbasic if s["name"] == "Breeding Pool")
        sg_score = next(s["score"] for s in nonbasic if s["name"] == "Simic Guildgate")
        assert bp_score > sg_score

    def test_suggest_lands_fetch_lands_score_well(self, seeded_db):
        """Fetch land with null produced_mana + search text should get color coverage."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        result = svc.suggest_lands(deck["deck_id"])
        nonbasic = result["suggestions"]["nonbasic"]
        ew = next((s for s in nonbasic if s["name"] == "Evolving Wilds"), None)
        assert ew is not None
        # Should detect all CI colors via search text
        assert set(ew["produced_mana"]) == {"W", "U", "B", "G"}

    def test_suggest_lands_respects_color_identity(self, seeded_db):
        """Off-CI land (Boros Garrison with R) should be excluded for Atraxa (WUBG)."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        result = svc.suggest_lands(deck["deck_id"])
        nonbasic_names = [s["name"] for s in result["suggestions"]["nonbasic"]]
        assert "Boros Garrison" not in nonbasic_names

    def test_suggest_lands_no_commander_errors(self, db):
        """suggest_lands should raise when no commander assigned."""
        deck_repo = DeckRepository(db)
        deck_id = deck_repo.add(Deck(id=None, name="No Commander"))
        db.commit()
        svc = DeckBuilderService(db)
        with pytest.raises(ValueError, match="No commander"):
            svc.suggest_lands(deck_id)

    def test_fill_lands_backward_compat(self, seeded_db):
        """fill_lands should auto-add all suggested lands (CLI backward compat)."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")

        result = svc.fill_lands(deck["deck_id"])
        assert result["added"] > 0
        assert "lands" in result
        # Should have added both nonbasic and basic lands
        total_in_deck = len(svc.deck_repo.get_cards(deck["deck_id"]))
        # Commander + STP + lands added
        assert total_in_deck == 1 + 1 + result["added"]


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


class TestReplacements:
    def _setup_replacement_fixture(self, seeded_db):
        """Add extra cards for replacement testing."""
        db, entries = seeded_db
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)
        collection_repo = CollectionRepository(db)
        set_repo = SetRepository(db)

        # Another 1-CMC artifact with ramp tag (replacement for Sol Ring)
        card_repo.upsert(Card(
            oracle_id="mindstone-id", name="Mind Stone",
            type_line="Artifact", mana_cost="{2}", cmc=2.0,
            oracle_text="{T}: Add {C}. {1}, {T}, Sacrifice Mind Stone: Draw a card.",
            colors=[], color_identity=[],
        ))
        printing_repo.upsert(Printing(
            printing_id="mindstone-p1", oracle_id="mindstone-id", set_code="cmd",
            collector_number="20", rarity="U",
            raw_json=json.dumps({"legalities": {"commander": "legal"}}),
        ))
        entries["mindstone-p1"] = collection_repo.add(
            CollectionEntry(id=None, printing_id="mindstone-p1", finish="nonfoil")
        )
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("mindstone-id", "ramp"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("mindstone-id", "mana-rock"))

        # Another 1-CMC instant, white, with removal tag (type-based for STP)
        card_repo.upsert(Card(
            oracle_id="pathtx-id", name="Path to Exile",
            type_line="Instant", mana_cost="{W}", cmc=1.0,
            oracle_text="Exile target creature.",
            colors=["W"], color_identity=["W"],
        ))
        printing_repo.upsert(Printing(
            printing_id="pathtx-p1", oracle_id="pathtx-id", set_code="cmd",
            collector_number="21", rarity="U",
            raw_json=json.dumps({"legalities": {"commander": "legal"}}),
        ))
        entries["pathtx-p1"] = collection_repo.add(
            CollectionEntry(id=None, printing_id="pathtx-p1", finish="nonfoil")
        )
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("pathtx-id", "removal"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("pathtx-id", "creature-removal"))

        # A red card at CMC 1 (off-CI for Atraxa)
        card_repo.upsert(Card(
            oracle_id="shock-id", name="Shock",
            type_line="Instant", mana_cost="{R}", cmc=1.0,
            oracle_text="Shock deals 2 damage.",
            colors=["R"], color_identity=["R"],
        ))
        printing_repo.upsert(Printing(
            printing_id="shock-p1", oracle_id="shock-id", set_code="m21",
            collector_number="22", rarity="C",
            raw_json=json.dumps({"legalities": {"commander": "legal"}}),
        ))
        entries["shock-p1"] = collection_repo.add(
            CollectionEntry(id=None, printing_id="shock-p1", finish="nonfoil")
        )
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("shock-id", "removal"))

        db.commit()
        return db, entries

    def test_get_replacements_role_based(self, seeded_db):
        """Cards with same plan tags + CMC should appear in role suggestions."""
        db, entries = self._setup_replacement_fixture(seeded_db)
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")

        # Add STP to deck, set plan with removal tag
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        svc.set_plan(deck["deck_id"], {"removal": 2})

        # Find the STP collection entry in the deck
        deck_cards = svc.deck_repo.get_cards(deck["deck_id"])
        stp_cid = [c["id"] for c in deck_cards if c["name"] == "Swords to Plowshares"][0]

        result = svc.get_replacements(deck["deck_id"], stp_cid)
        role_names = [c["name"] for c in result["role_suggestions"]]
        assert "Path to Exile" in role_names

    def test_get_replacements_type_based(self, seeded_db):
        """Cards with same type + CMC + color should appear in type suggestions."""
        db, entries = self._setup_replacement_fixture(seeded_db)
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")

        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        svc.set_plan(deck["deck_id"], {"removal": 2})

        deck_cards = svc.deck_repo.get_cards(deck["deck_id"])
        stp_cid = [c["id"] for c in deck_cards if c["name"] == "Swords to Plowshares"][0]

        result = svc.get_replacements(deck["deck_id"], stp_cid)
        type_names = [c["name"] for c in result["type_suggestions"]]
        # Path to Exile: same CMC=1, same color=[W], same type=Instant
        assert "Path to Exile" in type_names

    def test_get_replacements_no_plan_tags(self, seeded_db):
        """Card with no plan tags should return empty role suggestions."""
        db, entries = self._setup_replacement_fixture(seeded_db)
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")

        # Grizzly Bears has no plan-relevant tags
        svc.add_card(deck["deck_id"], "Grizzly Bears")
        svc.set_plan(deck["deck_id"], {"removal": 2})

        deck_cards = svc.deck_repo.get_cards(deck["deck_id"])
        bear_cid = [c["id"] for c in deck_cards if c["name"] == "Grizzly Bears"][0]

        result = svc.get_replacements(deck["deck_id"], bear_cid)
        assert result["role_suggestions"] == []
        # Type suggestions might still work (Creature at CMC 2)

    def test_get_replacements_excludes_deck_cards(self, seeded_db):
        """Cards already in the deck should not appear in suggestions."""
        db, entries = self._setup_replacement_fixture(seeded_db)
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")

        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        svc.add_card(deck["deck_id"], "Path to Exile")
        svc.set_plan(deck["deck_id"], {"removal": 2})

        deck_cards = svc.deck_repo.get_cards(deck["deck_id"])
        stp_cid = [c["id"] for c in deck_cards if c["name"] == "Swords to Plowshares"][0]

        result = svc.get_replacements(deck["deck_id"], stp_cid)
        all_names = ([c["name"] for c in result["role_suggestions"]] +
                     [c["name"] for c in result["type_suggestions"]])
        # Path to Exile is already in deck, should not be suggested
        assert "Path to Exile" not in all_names
        # STP itself should not be suggested
        assert "Swords to Plowshares" not in all_names

    def test_get_replacements_ci_filtering(self, seeded_db):
        """Cards outside commander CI should not appear."""
        db, entries = self._setup_replacement_fixture(seeded_db)
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")

        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        svc.set_plan(deck["deck_id"], {"removal": 2})

        deck_cards = svc.deck_repo.get_cards(deck["deck_id"])
        stp_cid = [c["id"] for c in deck_cards if c["name"] == "Swords to Plowshares"][0]

        result = svc.get_replacements(deck["deck_id"], stp_cid)
        all_names = ([c["name"] for c in result["role_suggestions"]] +
                     [c["name"] for c in result["type_suggestions"]])
        # Shock has R in CI, Atraxa is WUBG — Shock should be excluded
        assert "Shock" not in all_names
        # Lightning Bolt too
        assert "Lightning Bolt" not in all_names


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

    def test_autofill_reset_clears_non_commander_cards(self, seeded_db):
        """reset=True should remove non-commander cards before suggesting."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"ramp": 1, "removal": 1})

        # Add cards to deck
        svc.add_card(deck["deck_id"], "Sol Ring")
        svc.add_card(deck["deck_id"], "Swords to Plowshares")
        cards_before = svc.deck_repo.get_cards(deck["deck_id"])
        # Commander + Sol Ring + STP = 3
        assert len(cards_before) == 3

        # Autofill with reset — should remove Sol Ring and STP, then re-suggest them
        result = svc.autofill(deck["deck_id"], reset=True)
        # After reset, cards should have been removed (only commander remains)
        cards_after_reset = svc.deck_repo.get_cards(deck["deck_id"])
        assert len(cards_after_reset) == 1  # Only commander
        assert cards_after_reset[0]["deck_zone"] == "commander"

        # Suggestions should include ramp and removal (since deck is now empty)
        assert "ramp" in result["suggestions"]
        assert "removal" in result["suggestions"]

    def test_autofill_excludes_tokens(self, seeded_db):
        """Token cards should not appear in autofill suggestions."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        svc.set_plan(deck["deck_id"], {"type:spider": 1})
        result = svc.autofill(deck["deck_id"])

        # Spider token has the type:spider tag but should be filtered out
        suggestions = result["suggestions"]
        if "type:spider" in suggestions:
            names = [c["name"] for c in suggestions["type:spider"]["cards"]]
            assert "Spider" not in names, "Token cards should not be suggested"

    def test_autofill_respects_budget(self, seeded_db):
        """Total suggested cards should not exceed 99 - lands - commander."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Set targets that sum to more than available slots (budget = 99 - 1 - 37 = 61)
        svc.set_plan(deck["deck_id"], {
            "ramp": 30, "draw": 30, "removal": 30, "lands": 37,
        })
        result = svc.autofill(deck["deck_id"])

        total_suggested = sum(
            len(group["cards"]) for group in result["suggestions"].values()
        )
        land_target = 37
        max_nonland = 99 - 1 - land_target  # 61
        assert total_suggested <= max_nonland, (
            f"Suggested {total_suggested} cards but budget is {max_nonland}"
        )

    def test_autofill_cross_tag_counting(self, seeded_db):
        """A card picked for one tag should reduce need for other tags it satisfies."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Sol Ring has both "ramp" and "mana-rock" tags
        # If we need 1 ramp and 1 mana-rock, picking Sol Ring for ramp
        # should also satisfy mana-rock (cross-tag counting)
        svc.set_plan(deck["deck_id"], {"ramp": 1, "mana-rock": 1, "lands": 97})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        # Exclude creature fallback from the count — we're testing tag overlap
        tag_suggested = sum(
            len(group["cards"]) for tag, group in suggestions.items()
            if tag != "creatures"
        )
        # With cross-tag counting, Sol Ring picked for ramp satisfies mana-rock too
        # So tag-based suggestions should be 1 (not 2)
        assert tag_suggested == 1, (
            f"Expected 1 card (cross-tag), got {tag_suggested}: "
            f"{[(t, [c['name'] for c in g['cards']]) for t, g in suggestions.items()]}"
        )

    def test_autofill_creature_fallback(self, seeded_db):
        """When tag targets are filled but budget remains, fill with creatures."""
        db, entries = seeded_db
        svc = DeckBuilderService(db)
        deck = svc.create_deck("Atraxa, Praetors' Voice")
        # Small tag target leaves most of the budget unfilled
        svc.set_plan(deck["deck_id"], {"ramp": 1, "lands": 37})
        result = svc.autofill(deck["deck_id"])

        suggestions = result["suggestions"]
        assert "creatures" in suggestions, (
            f"Expected creature fallback, got tags: {list(suggestions.keys())}"
        )
        # Total should fill up to budget (99 - 1 commander - 37 lands = 61)
        total = sum(len(g["cards"]) for g in suggestions.values())
        assert total <= 61, f"Over budget: {total}"
        # Should have more than just the 1 ramp card
        assert total > 1, f"Fallback should have added creatures, got {total} total"


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
        """Unknown cards should be sent to Haiku for per-card validation."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import (
            TagValidator, TagValidation, TagResult,
        )

        validator = TagValidator(db)
        mock_response = MagicMock()
        mock_response.parsed_output = TagValidation(results=[
            TagResult(tag="ramp", valid=True),
            TagResult(tag="mana-rock", valid=True),
        ])
        validator.client.messages.parse = MagicMock(return_value=mock_response)

        candidates = [{"oracle_id": "solring-id", "name": "Sol Ring",
                       "type_line": "Artifact", "oracle_text": "Tap: Add {C}{C}."}]
        result = validator.validate_and_filter(candidates, "ramp")

        assert len(result) == 1
        validator.client.messages.parse.assert_called_once()

        # Check BOTH tags were cached
        row = db.execute(
            "SELECT valid FROM card_tag_validations WHERE oracle_id = ? AND tag = ?",
            ("solring-id", "ramp"),
        ).fetchone()
        assert row["valid"] == 1

        row2 = db.execute(
            "SELECT valid FROM card_tag_validations WHERE oracle_id = ? AND tag = ?",
            ("solring-id", "mana-rock"),
        ).fetchone()
        assert row2["valid"] == 1

    def test_type_tags_skip_haiku(self, seeded_db):
        """type: tags should be validated deterministically, not via Haiku."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import TagValidator

        # Insert type tags for Atraxa
        from mtg_collector.services.deck_builder.type_tags import insert_type_tags
        insert_type_tags(db)

        validator = TagValidator(db)
        validator.client = MagicMock()  # Should NOT be called

        candidates = [{"oracle_id": "atraxa-id", "name": "Atraxa, Praetors' Voice",
                       "type_line": "Legendary Creature — Phyrexian Angel Horror",
                       "oracle_text": "Flying, vigilance, deathtouch, lifelink"}]
        result = validator.validate_and_filter(candidates, "type:creature")

        assert len(result) == 1
        validator.client.messages.create.assert_not_called()

        # Verify it was cached
        row = db.execute(
            "SELECT valid, reason FROM card_tag_validations WHERE oracle_id = ? AND tag = ?",
            ("atraxa-id", "type:creature"),
        ).fetchone()
        assert row["valid"] == 1
        assert row["reason"] == "type_line check"

    def test_type_tag_filters_wrong_type(self, seeded_db):
        """type: validation should reject cards that don't have the type."""
        db, entries = seeded_db
        from unittest.mock import MagicMock
        from mtg_collector.services.deck_builder.tag_validator import TagValidator
        from mtg_collector.services.deck_builder.type_tags import insert_type_tags
        insert_type_tags(db)

        validator = TagValidator(db)
        validator.client = MagicMock()

        # Sol Ring is an Artifact, not a Spider
        candidates = [{"oracle_id": "solring-id", "name": "Sol Ring",
                       "type_line": "Artifact",
                       "oracle_text": "Tap: Add {C}{C}."}]
        result = validator.validate_and_filter(candidates, "type:spider")

        assert len(result) == 0
        validator.client.messages.create.assert_not_called()


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
            {"oracle_id": "solring-id", "name": "Cheap", "cmc": 1, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "0.25"}})},
            {"oracle_id": "stp-id", "name": "Mid", "cmc": 1, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
            {"oracle_id": "rhystic-id", "name": "Expensive", "cmc": 1, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
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
            {"oracle_id": "solring-id", "name": "Popular", "cmc": 2, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
            {"oracle_id": "stp-id", "name": "Obscure", "cmc": 2, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 10000, "prices": {"usd": "1.00"}})},
        ]
        scored = svc._score_candidates(candidates)

        popular = next(c for c in scored if c["name"] == "Popular")
        obscure = next(c for c in scored if c["name"] == "Obscure")

        # log2(100) ≈ 6.64, log2(10000) ≈ 13.29 — ratio ~2x, not 100x
        assert popular["_novelty"] == pytest.approx(math.log2(100), rel=0.01)
        assert obscure["_novelty"] == pytest.approx(math.log2(10000), rel=0.01)

    def test_score_with_per_commander_data(self, seeded_db):
        """When edhrec_data is provided, edhrec signal uses inclusion rate."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        edhrec_data = {
            "Staple Card": 0.80,   # 80% inclusion — high edhrec score
            "Hidden Gem": 0.02,    # 2% inclusion — low edhrec score
        }
        candidates = [
            {"oracle_id": "solring-id", "name": "Staple Card", "cmc": 2, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 5, "prices": {"usd": "1.00"}})},
            {"oracle_id": "stp-id", "name": "Hidden Gem", "cmc": 2, "tag_count": 1,
             "salt_score": 1.0, "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 5000, "prices": {"usd": "1.00"}})},
        ]
        scored = svc._score_candidates(candidates, edhrec_data=edhrec_data)

        staple = next(c for c in scored if c["name"] == "Staple Card")
        gem = next(c for c in scored if c["name"] == "Hidden Gem")

        # edhrec uses inclusion rate directly (higher = better for this commander)
        assert staple["_edhrec"] == 0.80
        assert gem["_edhrec"] == 0.02
        assert staple["_edhrec"] > gem["_edhrec"]

        # novelty still uses global rank (higher rank = more novel)
        assert staple["_novelty"] == pytest.approx(math.log2(5), rel=0.01)
        assert gem["_novelty"] == pytest.approx(math.log2(5000), rel=0.01)
        assert gem["_novelty"] > staple["_novelty"]

    def test_plan_overlap_boosts_multi_tag_cards(self, seeded_db):
        """Cards matching multiple plan categories should score higher."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)

        # Insert tags for two cards: one matches 3 plan tags, one matches 1
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("stp-id", "removal"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("stp-id", "creature-removal"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("rhystic-id", "draw"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("rhystic-id", "card-advantage"))
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("rhystic-id", "removal"))
        db.commit()

        plan_tags = {"removal", "draw", "card-advantage", "creature-removal"}

        candidates = [
            {"oracle_id": "stp-id", "name": "Swords to Plowshares",
             "cmc": 1, "tag_count": 2, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
            {"oracle_id": "rhystic-id", "name": "Rhystic Study",
             "cmc": 3, "tag_count": 3, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 100, "prices": {"usd": "1.00"}})},
        ]

        # Seed random for determinism
        random.seed(42)
        scored = svc._score_candidates(candidates, plan_tags=plan_tags)

        stp = next(c for c in scored if c["name"] == "Swords to Plowshares")
        rhystic = next(c for c in scored if c["name"] == "Rhystic Study")

        # Rhystic matches 3 plan tags (draw, card-advantage, removal)
        # StP matches 2 (removal, creature-removal)
        assert rhystic["_plan_overlap"] > stp["_plan_overlap"]

    def test_plan_overlap_respects_aliases(self, seeded_db):
        """Alias expansion should let cards match plan categories via related tags."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        from mtg_collector.services.deck_builder.service import TAG_ALIASES

        # Card has "mana-rock" tag (alias of "ramp")
        db.execute("INSERT OR IGNORE INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("solring-id", "mana-rock"))
        db.commit()

        # Plan has "ramp" — expanded plan_tags should include "mana-rock" via aliases
        plan_targets = {"ramp": 8, "draw": 6}
        expanded = set()
        for tag in plan_targets:
            expanded.add(tag)
            for alias in TAG_ALIASES.get(tag, []):
                expanded.add(alias)

        candidates = [
            {"oracle_id": "solring-id", "name": "Sol Ring",
             "cmc": 1, "tag_count": 1, "salt_score": 1.0,
             "released_at": "2024-01-01", "is_bling": 0,
             "raw_json": json.dumps({"edhrec_rank": 1, "prices": {"usd": "1.00"}})},
        ]

        scored = svc._score_candidates(candidates, plan_tags=expanded)
        sol = scored[0]

        # "mana-rock" is in expanded plan tags (alias of "ramp"), so overlap > 0
        assert sol["_plan_overlap"] >= 1
        assert "mana-rock" in expanded


# =============================================================================
# get_validated_tags
# =============================================================================

class TestGetValidatedTags:
    def test_no_tags_returns_empty(self, seeded_db):
        """Card with no tags returns empty list."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        result = svc.get_validated_tags("bolt-id")
        assert result["tags"] == []
        assert result["validated"] is False

    def test_returns_cached_validations(self, seeded_db):
        """Already-validated tags are returned from cache."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        # Use atraxa (unlikely to have leftover tags from other tests)
        db.execute("DELETE FROM card_tags WHERE oracle_id = 'atraxa-id'")
        db.execute("DELETE FROM card_tag_validations WHERE oracle_id = 'atraxa-id'")
        db.execute("INSERT INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("atraxa-id", "removal"))
        db.execute("INSERT INTO card_tag_validations "
                   "(oracle_id, tag, valid, reason, validated_at) VALUES (?, ?, ?, ?, ?)",
                   ("atraxa-id", "removal", 1, "Exiles a creature", "2024-01-01T00:00:00Z"))
        db.commit()

        result = svc.get_validated_tags("atraxa-id")
        assert len(result["tags"]) == 1
        removal = result["tags"][0]
        assert removal["tag"] == "removal"
        assert removal["valid"] is True
        assert removal["validated"] is True
        assert result["validated"] is True

    def test_unvalidated_without_api_key(self, seeded_db):
        """Without API key, unvalidated tags are returned as-is."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)  # no api_key
        db.execute("DELETE FROM card_tags WHERE oracle_id = 'atraxa-id'")
        db.execute("DELETE FROM card_tag_validations WHERE oracle_id = 'atraxa-id'")
        db.execute("INSERT INTO card_tags (oracle_id, tag) VALUES (?, ?)",
                   ("atraxa-id", "removal"))
        db.commit()

        result = svc.get_validated_tags("atraxa-id")
        assert len(result["tags"]) == 1
        assert result["tags"][0]["valid"] is None
        assert result["tags"][0]["validated"] is False
        assert result["validated"] is False


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
        assert "type:legendary" in tags  # legendary is a taggable supertype
        # Other supertypes like "basic" and "snow" are stripped
        tags2 = _parse_type_tags("Snow Creature — Bear")
        assert "type:snow" not in tags2

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
        # Atraxa should have creature, legendary, and subtypes
        tags = [r[0] for r in db.execute(
            "SELECT tag FROM card_tags WHERE oracle_id = 'atraxa-id' AND tag LIKE 'type:%'"
        ).fetchall()]
        assert "type:creature" in tags
        assert "type:legendary" in tags
        assert "type:angel" in tags


class TestCustomQueryTargets:
    """Tests for custom query plan targets and curve scoring."""

    def test_set_plan_custom_query_target(self, seeded_db):
        """set_plan accepts dict targets with count/query/label."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        targets = {
            "lands": 37,
            "ramp": 8,
            "creatures-with-deathtouch": {
                "count": 5,
                "query": "card.oracle_text LIKE '%deathtouch%' AND card.type_line LIKE '%Creature%'",
                "label": "Deathtouch Creatures",
            },
        }
        result = svc.set_plan(deck_id, targets)
        assert result["targets"]["ramp"]["count"] == 8
        assert result["targets"]["ramp"]["type"] == "tag"
        assert result["targets"]["creatures-with-deathtouch"]["count"] == 5
        assert result["targets"]["creatures-with-deathtouch"]["type"] == "query"

        # Verify it persists
        plan = svc.get_plan(deck_id)
        assert plan["targets"]["creatures-with-deathtouch"]["label"] == "Deathtouch Creatures"
        assert plan["targets"]["lands"]["type"] == "lands"

    def test_set_plan_rejects_invalid_custom_query(self, seeded_db):
        """set_plan rejects custom query targets with invalid SQL."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        targets = {
            "bad-query": {
                "count": 5,
                "query": "INVALID SQL GARBAGE HERE !!!",
                "label": "Bad Query",
            },
        }
        with pytest.raises(ValueError, match="Invalid custom query SQL"):
            svc.set_plan(deck_id, targets)

    def test_set_plan_rejects_mutation_query(self, seeded_db):
        """set_plan rejects custom queries containing mutation keywords."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        targets = {
            "evil": {
                "count": 5,
                "query": "1=1; DROP TABLE cards;--",
                "label": "Evil",
            },
        }
        with pytest.raises(ValueError, match="Forbidden SQL keyword"):
            svc.set_plan(deck_id, targets)

    def test_set_plan_rejects_missing_fields(self, seeded_db):
        """set_plan rejects dict targets missing required fields."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        targets = {
            "bad": {"count": 5, "query": "1=1"},  # missing "label"
        }
        with pytest.raises(ValueError, match="must have"):
            svc.set_plan(deck_id, targets)

    def test_plan_progress_custom_query(self, seeded_db):
        """_get_plan_progress counts matching cards for custom query targets."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        # Add a creature with deathtouch (Atraxa has it in oracle text)
        # Atraxa is already the commander — she matches "deathtouch"

        targets = {
            "lands": 37,
            "deathtouch": {
                "count": 5,
                "query": "card.oracle_text LIKE '%deathtouch%'",
                "label": "Deathtouch Cards",
            },
        }
        svc.set_plan(deck_id, targets)

        cards = svc.deck_repo.get_cards(deck_id)
        plan = svc.get_plan(deck_id)
        progress = svc._get_plan_progress(deck_id, cards, plan)

        # Atraxa is commander with "deathtouch" in text — should count
        assert progress["deathtouch"]["target"] == 5
        assert progress["deathtouch"]["current"] >= 1
        assert progress["deathtouch"]["label"] == "Deathtouch Cards"

    def test_query_custom_candidates(self, seeded_db):
        """_query_custom_candidates returns cards matching a WHERE clause."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]
        commander_ci = svc._get_commander_identity(deck_id)
        ci_clauses = svc._ci_exclusion_sql(commander_ci)

        # Query for artifacts
        results = svc._query_custom_candidates(
            "card.type_line LIKE '%Artifact%'",
            deck_id, commander_ci, ci_clauses, set(), limit=10,
        )
        names = [r["name"] for r in results]
        assert "Sol Ring" in names

    def test_compute_curve_state(self, seeded_db):
        """_compute_curve_state correctly buckets cards."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)
        deck_id = svc.create_deck("Atraxa, Praetors' Voice")["deck_id"]

        # Add some cards to the deck
        svc.add_card(deck_id, "Sol Ring")
        svc.add_card(deck_id, "Rhystic Study")

        cards = svc.deck_repo.get_cards(deck_id)
        state = svc._compute_curve_state(cards)

        # Sol Ring is CMC 1 noncreature (Artifact)
        assert state["noncreature"].get(1, 0) >= 1
        # Rhystic Study is CMC 3 noncreature (Enchantment)
        assert state["noncreature"].get(3, 0) >= 1

    def test_score_candidates_curve_fit(self, seeded_db):
        """Curve fit signal boosts cards in under-represented CMC buckets."""
        db, _ = seeded_db
        svc = DeckBuilderService(db)

        # Create two fake candidates at different CMCs
        candidates = [
            {
                "oracle_id": "solring-id", "name": "Sol Ring",
                "type_line": "Artifact", "mana_cost": "{1}", "cmc": 1.0,
                "oracle_text": "Tap: Add CC", "raw_json": _make_raw_json(edhrec_rank=1),
                "collection_id": 1, "released_at": "2020-01-01",
                "tag_count": 1, "salt_score": 1.0, "is_bling": 0,
            },
            {
                "oracle_id": "rhystic-id", "name": "Rhystic Study",
                "type_line": "Enchantment", "mana_cost": "{2}{U}", "cmc": 3.0,
                "oracle_text": "Draw a card", "raw_json": _make_raw_json(edhrec_rank=2),
                "collection_id": 2, "released_at": "2020-01-01",
                "tag_count": 1, "salt_score": 1.0, "is_bling": 0,
            },
        ]

        # Curve state with lots of 1-drops but no 3-drops
        curve_state = {
            "creature": {},
            "noncreature": {1: 10, 3: 0},
        }

        random.seed(42)
        scored = svc._score_candidates(candidates, curve_state=curve_state)
        by_name = {c["name"]: c for c in scored}

        # Rhystic Study (CMC 3, deficit 7) should have higher curve_fit
        # than Sol Ring (CMC 1, deficit 0 since 10 > target 7)
        assert by_name["Rhystic Study"]["_curve_fit"] > by_name["Sol Ring"]["_curve_fit"]


