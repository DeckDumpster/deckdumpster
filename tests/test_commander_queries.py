"""Deterministic tests for commander-sample-queries.py WHERE clauses.

Each test verifies that the SQL WHERE clause for a category/query returns
the expected well-known MTG Commander staple cards. Test cards are loaded
from a fixture of ~300 cards with real Scryfall oracle text.
"""

import json
import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load CATEGORIES from the commander-sample-queries script
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parents[1] / ".claude/skills/commander/scripts/commander-sample-queries.py"
_code = _SCRIPT.read_text().split("# --- Main ---")[0]
_ns: dict = {}
exec(_code, _ns)  # noqa: S102 — trusted project code
CATEGORIES = _ns["CATEGORIES"]

# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite DB with known cards
# ---------------------------------------------------------------------------
_FIXTURE = Path(__file__).resolve().parent / "fixtures/commander-query-cards.json"


@pytest.fixture(scope="module")
def db():
    """Create an in-memory SQLite DB populated with test cards."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE cards (
            oracle_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type_line TEXT,
            mana_cost TEXT,
            cmc REAL,
            oracle_text TEXT,
            colors TEXT,
            color_identity TEXT
        )"""
    )
    with open(_FIXTURE) as f:
        cards = json.load(f)
    for c in cards:
        conn.execute(
            "INSERT OR IGNORE INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (c["oracle_id"], c["name"], c["type_line"], c["mana_cost"],
             c["cmc"], c["oracle_text"], c["colors"], c["color_identity"]),
        )
    conn.commit()
    yield conn
    conn.close()


def _run_query(db, where_clause: str) -> set[str]:
    """Run a WHERE clause against the cards table and return matching names."""
    rows = db.execute(
        f"SELECT c.name FROM cards c WHERE {where_clause} ORDER BY c.name"
    ).fetchall()
    return {r[0] for r in rows}


# ===========================================================================
# RAMP
# ===========================================================================


class TestRamp:
    def test_mana_rocks_and_dorks(self, db):
        _, where = CATEGORIES["ramp"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Arcane Signet", "Birds of Paradise", "Bloom Tender",
            "Chromatic Lantern", "Chrome Mox", "Commander's Sphere",
            "Delighted Halfling", "Dimir Signet", "Elvish Archdruid",
            "Elvish Mystic", "Fellwar Stone", "Llanowar Elves",
            "Mana Vault", "Mind Stone", "Rakdos Signet",
            "Rishkar, Peema Renegade", "Sol Ring", "Talisman of Dominance",
            "Thought Vessel",
        }
        assert expected <= result

    def test_land_ramp_and_rituals(self, db):
        _, where = CATEGORIES["ramp"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Cultivate", "Dark Ritual", "Kodama's Reach",
            "Rampant Growth", "Sakura-Tribe Elder", "Solemn Simulacrum",
            "Wayfarer's Bauble",
        }
        assert expected <= result

    def test_cost_reducers(self, db):
        _, where = CATEGORIES["ramp"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Baral, Chief of Compliance", "Dragonspeaker Shaman",
            "Emerald Medallion", "Etherium Sculptor", "Foundry Inspector",
            "Goblin Electromancer", "Goblin Warchief", "Jet Medallion",
            "Pearl Medallion", "Ruby Medallion", "Sapphire Medallion",
        }
        assert expected <= result

    def test_treasure_and_sacrifice_for_mana(self, db):
        _, where = CATEGORIES["ramp"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Ashnod's Altar", "Deadly Dispute", "Dockside Extortionist",
            "Phyrexian Altar", "Pitiless Plunderer", "Ragavan, Nimble Pilferer",
            "Smothering Tithe", "Storm-Kiln Artist", "Tireless Provisioner",
        }
        assert expected <= result


# ===========================================================================
# CARD ADVANTAGE
# ===========================================================================


class TestCardAdvantage:
    def test_draw_spells_and_engines(self, db):
        _, where = CATEGORIES["card-advantage"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Brainstorm", "Consider", "Faithless Looting",
            "Frantic Search", "Harmonize", "Mystic Remora",
            "Night's Whisper", "Phyrexian Arena", "Ponder",
            "Preordain", "Read the Bones", "Rhystic Study",
            "Sign in Blood", "Sylvan Library", "Windfall",
        }
        assert expected <= result

    def test_creatures_that_draw(self, db):
        _, where = CATEGORIES["card-advantage"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Baleful Strix", "Beast Whisperer", "Elvish Visionary",
            "Esper Sentinel", "Faerie Mastermind", "Midnight Reaper",
            "Morbid Opportunist", "Mulldrifter", "Sheoldred, the Apocalypse",
            "Solemn Simulacrum", "Sram, Senior Edificer",
            "Toski, Bearer of Secrets", "Wall of Omens", "Welcoming Vampire",
        }
        assert expected <= result

    def test_impulse_draw_looting_equipment(self, db):
        _, where = CATEGORIES["card-advantage"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Faithless Looting", "Frantic Search", "Jeska's Will",
            "Key to the City", "Mask of Memory", "Outpost Siege",
            "Skullclamp", "Sword of Fire and Ice", "Thrill of Possibility",
            "Windfall",
        }
        assert expected <= result

    def test_surveil(self, db):
        _, where = CATEGORIES["card-advantage"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Consider", "Dragon's Rage Channeler",
            "Dimir Spybug", "Sinister Sabotage", "Thought Erasure",
        }
        assert expected <= result


# ===========================================================================
# TARGETED DISRUPTION
# ===========================================================================


class TestTargetedDisruption:
    def test_creature_removal(self, db):
        _, where = CATEGORIES["targeted-disruption"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Diabolic Edict", "Doom Blade", "Fatal Push",
            "Go for the Throat", "Path to Exile", "Pongify",
            "Rapid Hybridization", "Ravenous Chupacabra",
            "Swords to Plowshares", "Terminate",
        }
        assert expected <= result

    def test_permanent_removal(self, db):
        _, where = CATEGORIES["targeted-disruption"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Assassin's Trophy", "Beast Within", "Disenchant",
            "Generous Gift", "Naturalize", "Nature's Claim",
            "Reclamation Sage", "Return to Nature", "Vindicate",
        }
        assert expected <= result

    def test_burn(self, db):
        _, where = CATEGORIES["targeted-disruption"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Chain Lightning", "Lightning Bolt", "Rift Bolt",
            "Searing Blaze", "Fiery Temper",
        }
        assert expected <= result

    def test_counterspells_and_bounce(self, db):
        _, where = CATEGORIES["targeted-disruption"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Arcane Denial", "Counterspell", "Cyclonic Rift",
            "Mana Drain", "Unsummon", "Vapor Snag",
        }
        assert expected <= result


# ===========================================================================
# MASS DISRUPTION
# ===========================================================================


class TestMassDisruption:
    def test_board_wipes(self, db):
        _, where = CATEGORIES["mass-disruption"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Blasphemous Act", "Damnation", "Day of Judgment",
            "Farewell", "Supreme Verdict", "Wrath of God",
        }
        assert expected <= result

    def test_mass_minus_and_overload(self, db):
        _, where = CATEGORIES["mass-disruption"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Cyclonic Rift", "Languish", "Toxic Deluge",
        }
        assert expected <= result

    def test_opponents_sacrifice(self, db):
        _, where = CATEGORIES["mass-disruption"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Butcher of Malakir", "Dictate of Erebos", "Grave Pact",
        }
        assert expected <= result


# ===========================================================================
# LANDS
# ===========================================================================


class TestLands:
    def test_duals_and_fetches(self, db):
        _, where = CATEGORIES["lands"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Arid Mesa", "Blood Crypt", "Bloodstained Mire",
            "Breeding Pool", "Flooded Strand", "Godless Shrine",
            "Hallowed Fountain", "Marsh Flats", "Misty Rainforest",
            "Overgrown Tomb", "Polluted Delta", "Sacred Foundry",
            "Scalding Tarn", "Steam Vents", "Stomping Ground",
            "Temple Garden", "Verdant Catacombs", "Watery Grave",
            "Windswept Heath", "Wooded Foothills",
        }
        assert expected <= result

    def test_utility_lands(self, db):
        _, where = CATEGORIES["lands"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Field of the Dead", "Maze of Ith",
            "Nykthos, Shrine to Nyx",
        }
        assert expected <= result


# ===========================================================================
# SACRIFICE
# ===========================================================================


class TestSacrifice:
    def test_free_sacrifice_outlets(self, db):
        _, where = CATEGORIES["sacrifice"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Ashnod's Altar", "Carrion Feeder",
            "Phyrexian Altar", "Viscera Seer",
        }
        assert expected <= result

    def test_death_triggers(self, db):
        _, where = CATEGORIES["sacrifice"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Bastion of Remembrance", "Cruel Celebrant",
            "Vindictive Vampire", "Zulaport Cutthroat",
        }
        assert expected <= result

    def test_force_opponents_sacrifice(self, db):
        _, where = CATEGORIES["sacrifice"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Butcher of Malakir", "Crackling Doom",
            "Dictate of Erebos", "Sheoldred's Edict", "Soul Shatter",
        }
        assert expected <= result

    def test_dies_create_token(self, db):
        _, where = CATEGORIES["sacrifice"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Doomed Dissenter", "Hunted Witness",
            "Ministrant of Obligation", "Nested Shambler",
        }
        assert expected <= result

    def test_recursive_creatures(self, db):
        _, where = CATEGORIES["sacrifice"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Bloodghast", "Dread Wanderer",
            "Nether Traitor", "Reassembling Skeleton",
        }
        assert expected <= result


# ===========================================================================
# REANIMATION
# ===========================================================================


class TestReanimation:
    def test_reanimate_to_battlefield(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Breath of Life", "Karmic Guide",
            "Unburial Rites", "Zombify",
        }
        assert expected <= result

    def test_put_creature_from_graveyard(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][1]
        result = _run_query(db, where)
        expected = {"Necromancy", "Reanimate"}
        assert expected <= result

    def test_aura_reanimation(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][2]
        result = _run_query(db, where)
        expected = {"Animate Dead", "Dance of the Dead"}
        assert expected <= result

    def test_mass_reanimation(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Living Death", "Patriarch's Bidding",
            "Rally the Ancestors",
        }
        assert expected <= result

    def test_return_creature_to_hand(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Cadaver Imp", "Disentomb",
            "Gravedigger", "Raise Dead",
        }
        assert expected <= result

    def test_self_recurring_creatures(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][5]
        result = _run_query(db, where)
        expected = {
            "Bloodghast", "Dread Wanderer", "Karmic Guide",
            "Nether Traitor", "Reassembling Skeleton", "Sun Titan",
        }
        assert expected <= result

    def test_graveyard_fillers(self, db):
        _, where = CATEGORIES["reanimation"]["queries"][6]
        result = _run_query(db, where)
        expected = {
            "Buried Alive", "Entomb", "Final Parting",
            "Jarad's Orders", "Unmarked Grave",
        }
        assert expected <= result


# ===========================================================================
# TOKENS
# ===========================================================================


class TestTokens:
    def test_repeatable_token_generation(self, db):
        _, where = CATEGORIES["tokens"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Awakening Zone", "Bitterblossom",
            "Luminarch Ascension", "Ophiomancer",
            "Tendershoot Dryad",
        }
        assert expected <= result

    def test_token_doublers(self, db):
        _, where = CATEGORIES["tokens"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Anointed Procession", "Doubling Season",
            "Parallel Lives",
        }
        assert expected <= result

    def test_mass_token_generation(self, db):
        _, where = CATEGORIES["tokens"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Dragon Fodder", "Hordeling Outburst",
            "Krenko's Command", "Lingering Souls",
            "Rite of Replication", "Talrand's Invocation",
        }
        assert expected <= result

    def test_anthem_effects(self, db):
        _, where = CATEGORIES["tokens"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Dictate of Heliod", "Elvish Archdruid",
            "Gaea's Anthem", "Glorious Anthem",
            "Goblin Chieftain", "Merrow Reejerey",
            "Honor of the Pure", "Spear of Heliod",
            "Tempered Steel",
        }
        assert expected <= result

    def test_copy_or_populate(self, db):
        _, where = CATEGORIES["tokens"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Druid's Deliverance", "Growing Ranks",
            "Helm of the Host", "Rite of Replication",
            "Rootborn Defenses", "Second Harvest",
            "Trostani, Selesnya's Voice",
            "Vitu-Ghazi Guildmage",
        }
        assert expected <= result


# ===========================================================================
# COUNTERS
# ===========================================================================


class TestCounters:
    def test_put_counters(self, db):
        _, where = CATEGORIES["counters"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Carrion Feeder", "Experiment One",
            "Hangarback Walker", "Hardened Scales",
            "Managorger Hydra", "Pelt Collector",
            "Rishkar, Peema Renegade", "Walking Ballista",
        }
        assert expected <= result

    def test_enters_with_counters(self, db):
        _, where = CATEGORIES["counters"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Arcbound Ravager", "Arcbound Worker",
            "Hangarback Walker", "Metallic Mimic",
            "Servant of the Scale", "Stonecoil Serpent",
            "Walking Ballista",
        }
        assert expected <= result

    def test_counter_doublers(self, db):
        _, where = CATEGORIES["counters"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Branching Evolution", "Doubling Season",
        }
        assert expected <= result

    def test_proliferate(self, db):
        _, where = CATEGORIES["counters"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Atraxa, Praetors' Voice", "Contagion Clasp",
            "Contagion Engine", "Evolution Sage",
            "Flux Channeler", "Thrummingbird",
        }
        assert expected <= result

    def test_counter_payoffs(self, db):
        _, where = CATEGORIES["counters"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Champion of Lambholt", "Experiment One",
            "Fathom Mage", "Managorger Hydra",
            "Pelt Collector", "Soulherder", "Taurean Mauler",
        }
        assert expected <= result

    def test_counter_manipulation(self, db):
        _, where = CATEGORIES["counters"]["queries"][5]
        result = _run_query(db, where)
        expected = {"The Ozolith"}
        assert expected <= result


# ===========================================================================
# DISCARD
# ===========================================================================


class TestDiscard:
    def test_discard_enablers(self, db):
        _, where = CATEGORIES["discard"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Key to the City", "Putrid Imp",
            "Rummaging Goblin", "Thrill of Possibility",
            "Tormenting Voice", "Wild Mongrel",
        }
        assert expected <= result

    def test_madness_cards(self, db):
        _, where = CATEGORIES["discard"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Arrogant Wurm", "Basking Rootwalla",
            "Circular Logic", "Fiery Temper",
        }
        assert expected <= result

    def test_discard_payoffs(self, db):
        _, where = CATEGORIES["discard"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Bone Miser", "Surly Badgersaur",
            "Sword of Feast and Famine",
        }
        assert expected <= result

    def test_force_opponent_discard(self, db):
        _, where = CATEGORIES["discard"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Duress", "Fell Specter", "Liliana's Caress",
            "Megrim", "Waste Not",
        }
        assert expected <= result

    def test_graveyard_value(self, db):
        _, where = CATEGORIES["discard"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Ancient Grudge", "Deep Analysis",
            "Faithless Looting", "Lingering Souls",
            "Past in Flames", "Snapcaster Mage",
            "Unburial Rites",
        }
        assert expected <= result


# ===========================================================================
# ETB
# ===========================================================================


class TestETB:
    def test_etb_creatures_low_cmc(self, db):
        _, where = CATEGORIES["etb"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Baleful Strix", "Cadaver Imp",
            "Dockside Extortionist", "Elvish Visionary",
            "Eternal Witness", "Flickerwisp",
            "Imperial Recruiter", "Reclamation Sage",
            "Spellseeker", "Stoneforge Mystic",
            "Wall of Omens",
        }
        assert expected <= result

    def test_etb_creatures_mid_cmc(self, db):
        _, where = CATEGORIES["etb"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Acidic Slime", "Gravedigger", "Karmic Guide",
            "Mulldrifter", "Ravenous Chupacabra",
            "Restoration Angel", "Solemn Simulacrum",
            "Sun Titan", "Thragtusk",
        }
        assert expected <= result

    def test_blink_flicker(self, db):
        _, where = CATEGORIES["etb"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Conjurer's Closet", "Ephemerate", "Flickerwisp",
            "Ghostly Flicker", "Restoration Angel",
            "Soulherder", "Thassa, Deep-Dwelling",
        }
        assert expected <= result

    def test_etb_doublers(self, db):
        _, where = CATEGORIES["etb"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Elesh Norn, Mother of Machines",
            "Panharmonicon", "Yarok, the Desecrated",
        }
        assert expected <= result


# ===========================================================================
# VOLTRON
# ===========================================================================


class TestVoltron:
    def test_equipment_low_cmc(self, db):
        _, where = CATEGORIES["voltron"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Colossus Hammer", "Cranial Plating",
            "Lightning Greaves", "Loxodon Warhammer",
            "Mask of Memory", "Prowler's Helm",
            "Skullclamp", "Swiftfoot Boots",
            "Sword of Feast and Famine", "Sword of Fire and Ice",
            "Trailblazer's Boots", "Umezawa's Jitte",
            "Whispersilk Cloak",
        }
        assert expected <= result

    def test_equipment_power_boosting(self, db):
        _, where = CATEGORIES["voltron"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Colossus Hammer", "Embercleave",
            "Loxodon Warhammer", "Sword of Feast and Famine",
            "Sword of Fire and Ice", "Umezawa's Jitte",
        }
        assert expected <= result

    def test_auras_power_boosting(self, db):
        _, where = CATEGORIES["voltron"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "All That Glitters", "Ancestral Mask",
            "Daybreak Coronet", "Ethereal Armor",
            "Rancor", "Spirit Mantle", "Unflinching Courage",
        }
        assert expected <= result

    def test_evasion(self, db):
        _, where = CATEGORIES["voltron"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Aqueous Form", "Key to the City",
            "Prowler's Helm", "Trailblazer's Boots",
            "Whispersilk Cloak",
        }
        assert expected <= result

    def test_equipment_aura_tutors(self, db):
        _, where = CATEGORIES["voltron"]["queries"][4]
        result = _run_query(db, where)
        expected = {
            "Fighter Class", "Open the Armory",
            "Steelshaper's Gift", "Stoneforge Mystic",
            "Stonehewer Giant",
        }
        assert expected <= result


# ===========================================================================
# TRIBAL
# ===========================================================================


class TestTribal:
    def test_lords(self, db):
        _, where = CATEGORIES["tribal"]["queries"][0]
        result = _run_query(db, where)
        expected = {
            "Death Baron", "Elvish Archdruid",
            "Goblin Chieftain", "Merrow Reejerey",
        }
        assert expected <= result

    def test_tribal_cost_reduction(self, db):
        _, where = CATEGORIES["tribal"]["queries"][1]
        result = _run_query(db, where)
        expected = {
            "Baral, Chief of Compliance", "Dragonspeaker Shaman",
            "Etherium Sculptor", "Foundry Inspector",
            "Goblin Electromancer", "Goblin Warchief",
        }
        assert expected <= result

    def test_tribal_card_draw(self, db):
        _, where = CATEGORIES["tribal"]["queries"][2]
        result = _run_query(db, where)
        expected = {
            "Beast Whisperer", "Guardian Project",
            "Sram, Senior Edificer", "Vanquisher's Banner",
        }
        assert expected <= result

    def test_changelings(self, db):
        _, where = CATEGORIES["tribal"]["queries"][3]
        result = _run_query(db, where)
        expected = {
            "Amoeboid Changeling", "Chameleon Colossus",
            "Mirror Entity", "Realmwalker",
            "Taurean Mauler", "Unsettled Mariner",
        }
        assert expected <= result
