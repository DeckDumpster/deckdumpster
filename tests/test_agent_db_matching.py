"""Regression tests for the ingest agent's query_local_db matching layer.

Bug efj-mtgc-q29 / GitHub #222: the agent could not identify cards with accented
names. OCR reads "Éomer of the Riddermark" as "Eomer of the Riddermark", and
SQLite's built-in LIKE is not accent-insensitive, so every query the agent
emitted returned nothing and it gave up with {"cards": []}.

Two distinct defects are covered here:
  1. LIKE not matching across diacritics (fixed in the matching layer).
  2. set_code compared against an uppercase literal, while set codes are stored
     lowercase (fixed in the tool description the agent is prompted with).

Card names and set codes below are real values read out of the production
catalogue, not invented.
"""

import sqlite3

import pytest

from mtg_collector.services.agent import (
    _QUERY_TOOL_NOTES,
    _install_accent_insensitive_like,
    _tool_query_local_db,
)

# (oracle_id, name, set_code, collector_number) — verified present in prod.
CATALOGUE = [
    ("o-eomer", "Éomer of the Riddermark", "ltr", "121"),
    ("o-eomer", "Éomer of the Riddermark", "ltr", "572"),
    ("o-eomer", "Éomer of the Riddermark", "altr", "9"),
    ("o-baraddur", "Barad-dûr", "ltr", "425"),
    ("o-arwen", "Arwen Undómiel", "ltr", "194"),
    ("o-juzam", "Juzám Djinn", "arn", "29"),
    ("o-seance", "Séance", "dka", "20"),
    ("o-marton", "Márton Stromgald", "ice", "199"),
    ("o-arana", "Araña, Heart of the Spider", "spm", "4"),
    ("o-altair", "Altaïr Ibn-La'Ahad", "acr", "1"),
    ("o-bolt", "Lightning Bolt", "lea", "161"),
]


@pytest.fixture
def conn():
    """A connection configured exactly the way run_agent() configures its own."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE cards (oracle_id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE printings (
            printing_id TEXT PRIMARY KEY,
            oracle_id TEXT NOT NULL,
            set_code TEXT NOT NULL,
            collector_number TEXT NOT NULL
        );
        CREATE TABLE sets (set_code TEXT PRIMARY KEY, set_name TEXT, released_at TEXT);
    """)
    for oracle_id, name, set_code, cn in CATALOGUE:
        c.execute("INSERT OR IGNORE INTO cards VALUES (?, ?)", (oracle_id, name))
        c.execute(
            "INSERT INTO printings VALUES (?, ?, ?, ?)",
            (f"{set_code}-{cn}", oracle_id, set_code, cn),
        )
    _install_accent_insensitive_like(c)
    return c


def names_matching(conn, pattern):
    rows = conn.execute("SELECT name FROM cards WHERE name LIKE ?", (pattern,)).fetchall()
    return sorted(r["name"] for r in rows)


# --- Defect 1: accent-insensitive matching -------------------------------


def test_unaccented_query_matches_accented_name(conn):
    """The exact failure from the bug trace: OCR's 'Eomer' must find 'Éomer'."""
    assert names_matching(conn, "%Eomer of the Riddermark%") == [
        "Éomer of the Riddermark"
    ]


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ("%Barad-dur%", "Barad-dûr"),
        ("%Arwen Undomiel%", "Arwen Undómiel"),
        ("%Juzam Djinn%", "Juzám Djinn"),
        ("%Seance%", "Séance"),
        ("%Marton Stromgald%", "Márton Stromgald"),
        ("%Arana, Heart of the Spider%", "Araña, Heart of the Spider"),
        ("%Altair Ibn-La'Ahad%", "Altaïr Ibn-La'Ahad"),
    ],
)
def test_other_diacritics_match_unaccented_queries(conn, pattern, expected):
    """Diacritics beyond É: û, ó, á, é, ñ, ï all appear in the real catalogue."""
    assert names_matching(conn, pattern) == [expected]


def test_accented_query_matches_accented_name(conn):
    """The reverse direction: the correctly-accented spelling still matches."""
    assert names_matching(conn, "%Éomer of the Riddermark%") == [
        "Éomer of the Riddermark"
    ]


def test_accented_query_matches_unaccented_name(conn):
    """The other reverse: an over-accented guess must still find an ASCII name."""
    assert names_matching(conn, "%Lightning Bólt%") == ["Lightning Bolt"]


def test_matching_is_case_insensitive(conn):
    assert names_matching(conn, "%ÉOMER%") == ["Éomer of the Riddermark"]
    assert names_matching(conn, "%eomer%") == ["Éomer of the Riddermark"]


def test_non_matching_pattern_still_returns_nothing(conn):
    """Folding must not make LIKE promiscuous."""
    assert names_matching(conn, "%Llanowar Elves%") == []


# --- LIKE semantics must be preserved by the override --------------------


def test_underscore_wildcard_matches_single_character(conn):
    assert names_matching(conn, "S_ance") == ["Séance"]


def test_escape_clause_is_honoured(conn):
    rows = conn.execute(
        r"SELECT 'a%b' LIKE 'a\%b' ESCAPE '\' AS literal, "
        r"'axb' LIKE 'a\%b' ESCAPE '\' AS wildcard"
    ).fetchone()
    assert rows["literal"] == 1
    assert rows["wildcard"] == 0


def test_null_operands_yield_null(conn):
    row = conn.execute("SELECT NULL LIKE '%a%' AS a, 'x' LIKE NULL AS b").fetchone()
    assert row["a"] is None
    assert row["b"] is None


def test_non_text_column_still_matches(conn):
    """collector_number is TEXT but SQLite may hand the callback an int."""
    rows = conn.execute(
        "SELECT collector_number FROM printings WHERE collector_number LIKE '12%'"
    ).fetchall()
    assert [r["collector_number"] for r in rows] == ["121"]


# --- Defect 2: set codes are stored lowercase ----------------------------


def test_set_codes_are_stored_lowercase(conn):
    """The stored convention the agent's uppercase literal violated."""
    rows = conn.execute("SELECT DISTINCT set_code FROM printings").fetchall()
    codes = [r["set_code"] for r in rows]
    assert codes == [c.lower() for c in codes]


def test_lowercased_set_code_finds_the_card(conn):
    rows = conn.execute(
        "SELECT p.printing_id FROM cards c JOIN printings p ON p.oracle_id = c.oracle_id "
        "WHERE c.name LIKE '%Eomer%' AND p.set_code = 'ltr'"
    ).fetchall()
    assert sorted(r["printing_id"] for r in rows) == ["ltr-121", "ltr-572"]


def test_tool_description_warns_that_set_codes_are_lowercase():
    """The agent only learns the casing convention if we tell it."""
    notes = _QUERY_TOOL_NOTES.lower()
    assert "set_code" in notes
    assert "lowercase" in notes


def test_tool_description_states_like_is_accent_insensitive():
    """Stops the agent burning turns re-querying with a different spelling."""
    assert "accent-insensitive" in _QUERY_TOOL_NOTES.lower()


# --- End-to-end through the tool entry point -----------------------------


def test_bug_trace_query_now_returns_rows(conn):
    """Replay the SQL from the recorded failing trace for image 8848."""
    sql = (
        "SELECT p.printing_id, c.name, p.set_code, p.collector_number "
        "FROM cards c JOIN printings p ON p.oracle_id = c.oracle_id "
        "WHERE c.name LIKE '%Eomer of the Riddermark%'"
    )
    result = _tool_query_local_db(sql, conn)
    assert result != "No results found in local cache"
    assert "ltr-121" in result
    assert "Éomer of the Riddermark" in result
