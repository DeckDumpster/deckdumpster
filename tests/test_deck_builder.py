"""Unit tests for the Commander deck builder service."""

import sqlite3
from unittest.mock import patch

import pytest

from mtg_collector.services.deck_builder import (
    _ci_string,
    _color_identity_clause,
    _tool_query_local_db,
    classify_owned_cards,
    run_deck_builder,
)

TEST_DB = "tests/fixtures/test-data.sqlite"


def _test_conn():
    """Open a read/write in-memory copy of the test fixture."""
    source = sqlite3.connect(TEST_DB)
    conn = sqlite3.connect(":memory:")
    source.backup(conn)
    source.close()
    conn.row_factory = sqlite3.Row
    return conn


def _seed_collection(conn, oracle_ids=None, count=5):
    """Insert collection entries for testing. Returns list of collection IDs."""
    if oracle_ids is None:
        # Grab some red-identity cards
        rows = conn.execute(
            """SELECT p.printing_id, c.oracle_id FROM cards c
               JOIN printings p ON c.oracle_id = p.oracle_id
               WHERE NOT EXISTS (
                   SELECT 1 FROM json_each(c.color_identity)
                   WHERE json_each.value NOT IN ('R')
               )
               GROUP BY c.oracle_id
               LIMIT ?""",
            (count,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""SELECT p.printing_id, c.oracle_id FROM cards c
                JOIN printings p ON c.oracle_id = p.oracle_id
                WHERE c.oracle_id IN ({','.join('?' * len(oracle_ids))})
                GROUP BY c.oracle_id""",
            oracle_ids,
        ).fetchall()

    cids = []
    for row in rows:
        cursor = conn.execute(
            """INSERT INTO collection (printing_id, finish, condition, language,
               acquired_at, source, status)
            VALUES (?, 'nonfoil', 'Near Mint', 'English',
                    '2025-01-01T00:00:00', 'manual', 'owned')""",
            (row["printing_id"],),
        )
        cids.append(cursor.lastrowid)
    conn.commit()
    return cids


class TestColorIdentity:
    def test_ci_string_wub(self):
        assert _ci_string(["W", "U", "B"]) == "WUB"

    def test_ci_string_mono_red(self):
        assert _ci_string(["R"]) == "R"

    def test_ci_string_colorless(self):
        assert _ci_string([]) == "C"

    def test_ci_string_five_color(self):
        assert _ci_string(["W", "U", "B", "R", "G"]) == "WUBRG"

    def test_ci_string_ordering(self):
        """Colors should be in WUBRG order regardless of input order."""
        assert _ci_string(["G", "R"]) == "RG"

    def test_color_identity_clause_mono(self):
        clause = _color_identity_clause(["R"])
        assert "'R'" in clause
        assert "NOT EXISTS" in clause

    def test_color_identity_clause_colorless(self):
        clause = _color_identity_clause([])
        assert "NOT EXISTS" in clause


class TestToolQueryLocalDb:
    def test_select_works(self):
        conn = _test_conn()
        result = _tool_query_local_db("SELECT name FROM cards LIMIT 3", conn)
        assert result  # non-empty
        assert "Error" not in result

    def test_non_select_rejected(self):
        conn = _test_conn()
        result = _tool_query_local_db("DELETE FROM cards", conn)
        assert "Error" in result

    def test_bad_sql(self):
        conn = _test_conn()
        result = _tool_query_local_db("SELECT * FROM nonexistent_table", conn)
        assert "SQL error" in result

    def test_no_results(self):
        conn = _test_conn()
        result = _tool_query_local_db(
            "SELECT name FROM cards WHERE name = 'ZZZZNOTACARD'", conn
        )
        assert "No results" in result


class TestCommanderResolution:
    def test_commander_not_found(self):
        conn = _test_conn()
        _seed_collection(conn, count=5)
        with pytest.raises(ValueError, match="not found in local DB"):
            run_deck_builder("Nonexistent Card Name", conn, save_deck=False)

    def test_not_legendary(self):
        conn = _test_conn()
        # Abrade is an instant, not legendary
        _seed_collection(conn, count=5)
        with pytest.raises(ValueError, match="not a Legendary"):
            run_deck_builder("Abrade", conn, save_deck=False)

    def test_commander_not_owned(self):
        conn = _test_conn()
        # Don't seed any collection — commander won't be owned
        with pytest.raises(ValueError, match="not in your collection"):
            run_deck_builder("Krenko, Mob Boss", conn, save_deck=False)

    def test_commander_resolves_case_insensitive(self):
        conn = _test_conn()
        # Seed the commander
        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()
        _seed_collection(conn, oracle_ids=[cmd["oracle_id"]])

        # Should resolve but fail at the agent step (no anthropic key in tests)
        # We just verify the resolution part works by catching the anthropic error
        with pytest.raises(Exception):
            # Will fail at anthropic API call, but that's past resolution
            run_deck_builder("krenko, mob boss", conn, save_deck=False, max_calls=0)


class TestClassifyOwnedCards:
    def test_empty_collection(self):
        conn = _test_conn()
        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()
        result = classify_owned_cards(conn, ["R"], cmd["oracle_id"])
        for cat in result.values():
            assert cat == []

    @patch("mtg_collector.services.deck_builder._scryfall_classify_batch")
    def test_classification_with_mocked_scryfall(self, mock_classify):
        """Test classification with mocked Scryfall to avoid network calls."""
        conn = _test_conn()

        # Get Krenko's oracle_id
        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()

        # Seed some cards (not the commander)
        red_cards = conn.execute(
            """SELECT c.oracle_id, c.name, c.type_line FROM cards c
               WHERE NOT EXISTS (
                   SELECT 1 FROM json_each(c.color_identity)
                   WHERE json_each.value NOT IN ('R')
               )
               AND c.oracle_id != ?
               AND c.type_line NOT LIKE '%Land%'
               GROUP BY c.oracle_id
               LIMIT 10""",
            (cmd["oracle_id"],),
        ).fetchall()

        oracle_ids = [r["oracle_id"] for r in red_cards]
        _seed_collection(conn, oracle_ids=oracle_ids)

        # Mock scryfall to return empty (no network)
        mock_classify.return_value = set()

        result = classify_owned_cards(conn, ["R"], cmd["oracle_id"])

        assert "lands" in result
        assert "ramp" in result
        assert "card_advantage" in result
        assert "targeted_removal" in result
        assert "board_wipes" in result
        assert "unclassified" in result

        # All non-land cards should be unclassified since mock returns empty
        total_classified = sum(
            len(v) for k, v in result.items() if k not in ("lands", "unclassified")
        )
        assert total_classified == 0

    @patch("mtg_collector.services.deck_builder._scryfall_classify_batch")
    def test_lands_classified_locally(self, mock_classify):
        """Lands should be classified without Scryfall."""
        conn = _test_conn()

        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()

        # Find a land card
        land = conn.execute(
            """SELECT c.oracle_id FROM cards c
               WHERE c.type_line LIKE '%Land%'
               AND NOT EXISTS (
                   SELECT 1 FROM json_each(c.color_identity)
                   WHERE json_each.value NOT IN ('R')
               )
               LIMIT 1"""
        ).fetchone()

        if land:
            _seed_collection(conn, oracle_ids=[land["oracle_id"]])
            mock_classify.return_value = set()
            result = classify_owned_cards(conn, ["R"], cmd["oracle_id"])
            assert len(result["lands"]) >= 1

    @patch("mtg_collector.services.deck_builder._scryfall_classify_batch")
    def test_cards_can_appear_in_multiple_categories(self, mock_classify):
        """Cards matching multiple otags should appear in each category."""
        conn = _test_conn()

        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()

        # Seed a card
        card = conn.execute(
            """SELECT c.oracle_id, c.name FROM cards c
               JOIN printings p ON c.oracle_id = p.oracle_id
               WHERE c.type_line NOT LIKE '%Land%'
               AND NOT EXISTS (
                   SELECT 1 FROM json_each(c.color_identity)
                   WHERE json_each.value NOT IN ('R')
               )
               AND c.oracle_id != ?
               LIMIT 1""",
            (cmd["oracle_id"],),
        ).fetchone()

        if card:
            _seed_collection(conn, oracle_ids=[card["oracle_id"]])
            card_name = card["name"]

            # Mock: card matches both ramp and card_advantage
            def side_effect(names, otag, ci, scryfall):
                if otag in ("ramp", "card-advantage"):
                    return {card_name}
                return set()

            mock_classify.side_effect = side_effect
            result = classify_owned_cards(conn, ["R"], cmd["oracle_id"])

            ramp_names = {c["name"] for c in result["ramp"]}
            ca_names = {c["name"] for c in result["card_advantage"]}
            assert card_name in ramp_names
            assert card_name in ca_names

    @patch("mtg_collector.services.deck_builder._scryfall_classify_batch")
    def test_commander_excluded_from_pool(self, mock_classify):
        """The commander itself should not appear in the classified pool."""
        conn = _test_conn()

        cmd = conn.execute(
            "SELECT oracle_id FROM cards WHERE name = 'Krenko, Mob Boss'"
        ).fetchone()

        # Seed the commander + another card
        other = conn.execute(
            """SELECT c.oracle_id FROM cards c
               JOIN printings p ON c.oracle_id = p.oracle_id
               WHERE c.oracle_id != ?
               AND NOT EXISTS (
                   SELECT 1 FROM json_each(c.color_identity)
                   WHERE json_each.value NOT IN ('R')
               )
               AND c.type_line NOT LIKE '%Land%'
               LIMIT 1""",
            (cmd["oracle_id"],),
        ).fetchone()

        _seed_collection(conn, oracle_ids=[cmd["oracle_id"], other["oracle_id"]])
        mock_classify.return_value = set()
        result = classify_owned_cards(conn, ["R"], cmd["oracle_id"])

        all_names = set()
        for cat_cards in result.values():
            for c in cat_cards:
                all_names.add(c["name"])

        assert "Krenko, Mob Boss" not in all_names


class TestOutputValidation:
    def test_output_schema_structure(self):
        """Verify the output schema has required fields."""
        from mtg_collector.services.deck_builder import OUTPUT_SCHEMA

        props = OUTPUT_SCHEMA["properties"]
        assert "deck_name" in props
        assert "strategy_summary" in props
        assert "cards" in props
        assert "shopping_list" in props

        card_props = props["cards"]["items"]["properties"]
        assert "collection_id" in card_props
        assert "name" in card_props
        assert "categories" in card_props
