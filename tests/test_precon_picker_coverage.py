"""
Regression test: every row in mtgjson_decks is returned by exactly one of
kind=jumpstart or kind=precon.

Previously _PRECON_TYPES was an allowlist, so any MTGJSON deck type not in
that list — including future types and type IS NULL — would fall between the
two tabs and be unreachable in the New Deck modal (db-z04g).

The fix inverts the precon predicate to: type IS NULL OR type NOT IN
_JUMPSTART_TYPES, so every row belongs to exactly one kind.

To run: uv run pytest tests/test_precon_picker_coverage.py -v
"""

import os
import sqlite3
import tempfile

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.cli.crack_pack_server import CrackPackHandler


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_EMPTY_DECK_DATA = '{"mainBoard":[],"sideBoard":[],"commander":[]}'


def _build_db(rows):
    """Return a temp-file sqlite3 connection seeded with mtgjson_decks rows."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.executemany(
        """INSERT INTO mtgjson_decks
               (set_code, name, base_name, variation, type, main_count, release_date, deck_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(*r, _EMPTY_DECK_DATA) for r in rows],
    )
    conn.commit()
    return conn, path


def _all_names(conn, predicate, bind_params):
    return {
        r["name"]
        for r in conn.execute(
            f"SELECT name FROM mtgjson_decks WHERE {predicate}", bind_params
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# predicate helper — call the method directly without HTTP
# ---------------------------------------------------------------------------

def _kind_predicate(kind: str, col: str = "type"):
    """Thin wrapper so tests don't need a live server instance."""
    return CrackPackHandler._precon_kind_predicate(CrackPackHandler, kind, col)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

DECK_ROWS = [
    # set_code, name, base_name, variation, type, main_count, release_date
    ("m21", "Commander Draft A",  "Commander Draft A",  None, "Commander Deck",  100, "2020-07-03"),
    ("m21", "Theme Intro B",      "Theme Intro B",      None, "Theme Deck",       60, "2020-07-03"),
    ("j21", "Elf Warrior v1",     "Elf Warrior",        1,    "Jumpstart",        60, "2021-07-23"),
    ("j21", "Elf Warrior v2",     "Elf Warrior",        2,    "Jumpstart",        60, "2021-07-23"),
    # Unknown type — was invisible before the fix (db-z04g)
    ("tla", "Avatar Beginner",    "Avatar Beginner",    None, "Bundle Land Pack", 60, "2024-09-06"),
    # NULL type — was also invisible because bare NOT IN evaluates to NULL
    ("xyz", "Mystery Deck",       "Mystery Deck",       None, None,               60, "2025-01-01"),
]


@pytest.fixture
def conn_and_path():
    conn, path = _build_db(DECK_ROWS)
    yield conn, path
    conn.close()
    os.unlink(path)


def test_every_deck_covered_by_exactly_one_kind(conn_and_path):
    """The union of jumpstart + precon must equal the full table, with no overlap."""
    conn, _ = conn_and_path

    js_pred, js_params = _kind_predicate("jumpstart")
    pre_pred, pre_params = _kind_predicate("precon")

    jumpstart_names = _all_names(conn, js_pred, js_params)
    precon_names    = _all_names(conn, pre_pred, pre_params)
    all_names       = {r["name"] for r in conn.execute("SELECT name FROM mtgjson_decks").fetchall()}

    assert jumpstart_names | precon_names == all_names, (
        f"Decks not covered by either kind: {all_names - jumpstart_names - precon_names}"
    )
    assert jumpstart_names & precon_names == set(), (
        f"Decks in both kinds: {jumpstart_names & precon_names}"
    )


def test_unknown_type_appears_under_precon(conn_and_path):
    """A deck with a type not in either original list must surface under precon."""
    conn, _ = conn_and_path
    pre_pred, pre_params = _kind_predicate("precon")
    precon_names = _all_names(conn, pre_pred, pre_params)
    assert "Avatar Beginner" in precon_names


def test_null_type_appears_under_precon(conn_and_path):
    """A deck with type IS NULL must surface under precon."""
    conn, _ = conn_and_path
    pre_pred, pre_params = _kind_predicate("precon")
    precon_names = _all_names(conn, pre_pred, pre_params)
    assert "Mystery Deck" in precon_names


def test_jumpstart_type_does_not_appear_under_precon(conn_and_path):
    """Jumpstart decks must not appear under precon."""
    conn, _ = conn_and_path
    pre_pred, pre_params = _kind_predicate("precon")
    precon_names = _all_names(conn, pre_pred, pre_params)
    assert "Elf Warrior v1" not in precon_names
    assert "Elf Warrior v2" not in precon_names


def test_jumpstart_type_appears_under_jumpstart(conn_and_path):
    """Jumpstart decks must appear under jumpstart."""
    conn, _ = conn_and_path
    js_pred, js_params = _kind_predicate("jumpstart")
    jumpstart_names = _all_names(conn, js_pred, js_params)
    assert "Elf Warrior v1" in jumpstart_names
    assert "Elf Warrior v2" in jumpstart_names
