"""Tests for bulk-import tolerance in `mtg cache all`.

Scryfall occasionally reassigns a printing_id to a new (set_code,
collector_number) — most commonly when preview cards are folded into a
freshly-released set. That trips the printings.printing_id PK and used
to abort the entire bulk-import loop, starving Steps 5-6 (mark_cached +
per-set backfill) so newly-released sets stayed silently under-populated.

The fix wraps each per-row upsert in try/except IntegrityError so one
bad row logs+skips instead of aborting the pass.

To run: uv run pytest tests/test_printing_upsert.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.cli.cache_cmd import _upsert_card_row
from mtg_collector.db import (
    CardRepository,
    PrintingRepository,
    get_connection,
    init_db,
)
from mtg_collector.db.models import Card, Printing
from mtg_collector.services.scryfall import ScryfallAPI


def _card_data(id_, set_code, cn, oracle_id="oracle-1", name="Test Card"):
    return {
        "id": id_,
        "oracle_id": oracle_id,
        "name": name,
        "layout": "normal",
        "set": set_code,
        "collector_number": cn,
        "lang": "en",
        "cmc": 1.0,
        "type_line": "Instant",
        "mana_cost": "{R}",
        "colors": ["R"],
        "color_identity": ["R"],
        "rarity": "common",
        "finishes": ["nonfoil"],
    }


@pytest.fixture
def db():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    conn = get_connection(tmp.name)
    init_db(conn)
    for code in ("preview", "msh"):
        conn.execute(
            "INSERT INTO sets (set_code, set_name, set_type, released_at) VALUES (?, ?, ?, ?)",
            (code, code.upper(), "expansion", "2026-06-26"),
        )
    conn.commit()
    yield conn
    conn.close()
    Path(tmp.name).unlink(missing_ok=True)


class TestBulkUpsertTolerance:
    def test_new_card_upserts_successfully(self, db):
        api = ScryfallAPI()
        skipped = []
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)

        ok = _upsert_card_row(api, _card_data("pid-1", "msh", "1"),
                              card_repo, printing_repo, skipped)
        assert ok is True
        assert skipped == []
        assert printing_repo.get("pid-1") is not None

    def test_printing_id_reshuffle_across_sets_is_skipped_not_raised(self, db):
        """The prod failure mode: same printing_id, new (set, cn). Old upsert
        raised UNIQUE constraint failed: printings.printing_id and killed
        the whole cache run."""
        api = ScryfallAPI()
        skipped = []
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)

        _upsert_card_row(api, _card_data("pid-shared", "preview", "1"),
                         card_repo, printing_repo, skipped)
        assert skipped == []

        ok = _upsert_card_row(api, _card_data("pid-shared", "msh", "100"),
                              card_repo, printing_repo, skipped)
        assert ok is False
        assert len(skipped) == 1
        pid, sc, cn, err = skipped[0]
        assert pid == "pid-shared"
        assert sc == "msh"
        assert cn == "100"
        assert "printing_id" in err

    def test_loop_continues_past_bad_row(self, db):
        """A single bad row must not stop subsequent good rows — this is the
        whole point of the fix, since the old code aborted the entire pass."""
        api = ScryfallAPI()
        skipped = []
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)

        rows = [
            _card_data("pid-a", "msh", "1", oracle_id="o-a", name="A"),
            _card_data("pid-b", "preview", "1", oracle_id="o-b", name="B"),
            _card_data("pid-b", "msh", "50", oracle_id="o-b", name="B"),  # reshuffle
            _card_data("pid-c", "msh", "2", oracle_id="o-c", name="C"),
            _card_data("pid-d", "msh", "3", oracle_id="o-d", name="D"),
        ]
        succeeded = sum(
            _upsert_card_row(api, r, card_repo, printing_repo, skipped) for r in rows
        )

        assert succeeded == 4
        assert len(skipped) == 1
        for pid in ("pid-a", "pid-c", "pid-d"):
            assert printing_repo.get(pid) is not None
        assert printing_repo.get_by_set_cn("preview", "1") is not None

    def test_repeated_identical_row_upserts_without_skip(self, db):
        """Plain idempotent re-upsert (same PK, same everything) must succeed
        via the existing ON CONFLICT clause, not be caught as a skip."""
        api = ScryfallAPI()
        skipped = []
        card_repo = CardRepository(db)
        printing_repo = PrintingRepository(db)

        row = _card_data("pid-1", "msh", "1")
        for _ in range(3):
            assert _upsert_card_row(api, row, card_repo, printing_repo, skipped) is True

        assert skipped == []
        cnt = db.execute("SELECT COUNT(*) FROM printings").fetchone()[0]
        assert cnt == 1
