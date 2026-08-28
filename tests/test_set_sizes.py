"""sets.base_set_size / sets.total_set_size, their ingest sources and the migration (de-igx).

The columns exist because the base/boosterfun boundary cannot be derived.  The
obvious heuristic -- plain integer, black border, no frame_effects, not promo --
puts fin's boundary at #6, because `frame_effects=["legendary"]` is an ordinary
base-set frame.  MTGJSON says 309.  These tests pin the stored value and the
counting rule that reads it.

To run: uv run pytest tests/test_set_sizes.py -v
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtg_collector.db.models import Set, SetRepository
from mtg_collector.db.schema import (
    SCHEMA_VERSION,
    SchemaIntegrityError,
    get_current_version,
    init_db,
)
from mtg_collector.db.set_backfill import apply_base_set_sizes, apply_total_set_sizes
from mtg_collector.db.set_index import set_index
from mtg_collector.services.bulk_import import ScryfallBulkClient

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"

#: fin, as prod holds it: 309 is the last base-set number, 599 printings in all.
FIN_BASE_SET_SIZE = 309
FIN_TOTAL_SET_SIZE = 599
#: ...but 311 printings sit at or below 309, because 123a/123b share a number.
FIN_BASE_PRINTINGS = 311


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name) VALUES ('fin', 'Final Fantasy')"
    )
    conn.commit()
    yield conn
    conn.close()


def _mtgjson(**sets):
    """AllPrintings.json's `data` object, reduced to what the sizes are read from."""
    return {code.upper(): payload for code, payload in sets.items()}


def _seed_fin_printings(conn):
    """599 printings: 309 plain base numbers, 123a/123b, and 288 boosterfun.

    Faithful to the shape the counting rule has to survive, not to fin's actual
    card names.
    """
    conn.execute(
        "INSERT INTO cards (oracle_id, name) VALUES ('oracle-fin', 'Placeholder')"
    )
    numbers = [str(n) for n in range(1, FIN_BASE_SET_SIZE + 1)]
    numbers += ["123a", "123b"]
    numbers += [str(n) for n in range(FIN_BASE_SET_SIZE + 1, 598)]
    conn.executemany(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number)"
        " VALUES (?, 'oracle-fin', 'fin', ?)",
        [(f"fin-{cn}", cn) for cn in numbers],
    )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM printings WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_TOTAL_SET_SIZE


# ── The stored boundary ──


def test_fin_resolves_to_base_set_size_309(db):
    """MTGJSON's baseSetSize lands on the row, unmodified."""
    apply_base_set_sizes(db, _mtgjson(fin={"baseSetSize": FIN_BASE_SET_SIZE}))

    assert db.execute(
        "SELECT base_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_BASE_SET_SIZE


def test_scryfall_card_count_becomes_total_set_size(db):
    apply_total_set_sizes(db, [{"code": "fin", "card_count": FIN_TOTAL_SET_SIZE}])

    assert db.execute(
        "SELECT total_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_TOTAL_SET_SIZE


def test_to_set_model_keeps_the_card_count_it_used_to_discard():
    """The Scryfall ingest path carries the size, not just the validation count."""
    model = ScryfallBulkClient().to_set_model(
        {"code": "fin", "name": "Final Fantasy", "card_count": FIN_TOTAL_SET_SIZE}
    )

    assert model.total_set_size == FIN_TOTAL_SET_SIZE


# ── The counting rule ──


def test_base_completion_counts_printings_not_the_boundary(db):
    """309 is where the base set ends, not how many printings are in it.

    Suffixed numbers (123a, 123b) sit inside the base range, so fin's base
    section holds 311 printings.  Using base_set_size as the denominator reads
    309/309 on a complete binder with two empty pockets in it.
    """
    _seed_fin_printings(db)
    apply_base_set_sizes(db, _mtgjson(fin={"baseSetSize": FIN_BASE_SET_SIZE}))

    total_base = db.execute(
        """
        SELECT COUNT(*) FROM printings p
        JOIN sets s ON s.set_code = p.set_code
        WHERE p.set_code = 'fin'
          AND CAST(p.collector_number AS INTEGER) <= s.base_set_size
        """
    ).fetchone()[0]

    assert total_base == FIN_BASE_PRINTINGS
    assert total_base != FIN_BASE_SET_SIZE


# ── NULL is a value, not a gap ──


def test_a_set_mtgjson_does_not_carry_stays_null(db):
    apply_base_set_sizes(db, _mtgjson(oth={"baseSetSize": 250}))

    assert db.execute(
        "SELECT base_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] is None


def test_card_count_zero_is_an_absence_not_a_size(db):
    """Scryfall reports 0 for an announced but unspoiled set; 0/0 is the NaN."""
    apply_total_set_sizes(db, [{"code": "fin", "card_count": 0}])

    assert db.execute(
        "SELECT total_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] is None


def test_a_missing_size_never_blanks_a_stored_one(db):
    apply_total_set_sizes(db, [{"code": "fin", "card_count": FIN_TOTAL_SET_SIZE}])
    apply_total_set_sizes(db, [{"code": "fin"}])

    assert db.execute(
        "SELECT total_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_TOTAL_SET_SIZE


# ── Backfill mechanics: idempotent, batched, UPDATE-only ──


def test_rerunning_the_backfill_writes_nothing(db):
    payload = _mtgjson(fin={"baseSetSize": FIN_BASE_SET_SIZE})

    assert apply_base_set_sizes(db, payload) == 1
    assert apply_base_set_sizes(db, payload) == 0


def test_backfill_never_invents_a_set(db):
    """A set with no local printings is not a set the binder can render."""
    changed = apply_base_set_sizes(db, _mtgjson(zzz={"baseSetSize": 100}))

    assert changed == 0
    assert db.execute(
        "SELECT COUNT(*) FROM sets WHERE set_code = 'zzz'"
    ).fetchone()[0] == 0


def test_backfill_batches_cover_every_set(db):
    """A batch size below the input length must not truncate the run."""
    codes = [f"s{n:03d}" for n in range(500)]
    db.executemany(
        "INSERT INTO sets (set_code, set_name) VALUES (?, ?)",
        [(c, c.upper()) for c in codes],
    )
    db.commit()

    changed = apply_total_set_sizes(
        db, [{"code": c, "card_count": 100} for c in codes], batch_size=7
    )

    assert changed == len(codes)
    assert db.execute(
        "SELECT COUNT(*) FROM sets WHERE total_set_size = 100"
    ).fetchone()[0] == len(codes)


def test_a_size_change_is_applied(db):
    """Idempotence is 'no write when unchanged', not 'write once ever'."""
    apply_total_set_sizes(db, [{"code": "fin", "card_count": 598}])
    assert apply_total_set_sizes(
        db, [{"code": "fin", "card_count": FIN_TOTAL_SET_SIZE}]
    ) == 1

    assert db.execute(
        "SELECT total_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()[0] == FIN_TOTAL_SET_SIZE


# ── The two sources write different columns and must not fight ──


def test_a_scryfall_upsert_does_not_wipe_the_mtgjson_column(db):
    """`mtg cache all` knows total_set_size and nothing about base_set_size."""
    apply_base_set_sizes(db, _mtgjson(fin={"baseSetSize": FIN_BASE_SET_SIZE}))

    SetRepository(db).upsert(
        Set(
            set_code="fin",
            set_name="Final Fantasy",
            total_set_size=FIN_TOTAL_SET_SIZE,
        )
    )
    db.commit()

    row = db.execute(
        "SELECT base_set_size, total_set_size FROM sets WHERE set_code = 'fin'"
    ).fetchone()
    assert row["base_set_size"] == FIN_BASE_SET_SIZE
    assert row["total_set_size"] == FIN_TOTAL_SET_SIZE


def test_repository_reads_the_sizes_back(db):
    apply_base_set_sizes(db, _mtgjson(fin={"baseSetSize": FIN_BASE_SET_SIZE}))
    apply_total_set_sizes(db, [{"code": "fin", "card_count": FIN_TOTAL_SET_SIZE}])

    loaded = SetRepository(db).get("fin")

    assert loaded.base_set_size == FIN_BASE_SET_SIZE
    assert loaded.total_set_size == FIN_TOTAL_SET_SIZE


# ── The migration ──


def test_fresh_db_is_at_the_current_version_with_both_columns(db):
    assert get_current_version(db) == SCHEMA_VERSION
    columns = {row[1] for row in db.execute("PRAGMA table_info(sets)")}
    assert {"base_set_size", "total_set_size"} <= columns


def test_init_db_on_an_existing_db_does_not_raise(db):
    """The version is current and the objects are intact — nothing to report."""
    assert init_db(db) is False


def test_the_fixture_upgrades_across_versions(tmp_path):
    """The committed fixture is deliberately old; it must migrate, not break.

    It predates printings.card_name, so this walks several migrations rather
    than only the new one — a fresh DB never exercises that path at all.
    """
    upgraded = tmp_path / "test-data.sqlite"
    shutil.copy(FIXTURE_DB, upgraded)

    conn = sqlite3.connect(upgraded)
    conn.row_factory = sqlite3.Row
    before = get_current_version(conn)
    assert before < SCHEMA_VERSION, "fixture is no longer old enough to prove anything"
    sets_before = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]

    assert init_db(conn) is True
    assert get_current_version(conn) == SCHEMA_VERSION

    columns = {row[1] for row in conn.execute("PRAGMA table_info(sets)")}
    assert {"base_set_size", "total_set_size"} <= columns
    assert conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == sets_before

    # The integrity check is what turns a half-applied migration into a loud
    # failure, so run the boot path a second time against the upgraded file.
    try:
        assert init_db(conn) is False
    except SchemaIntegrityError as exc:  # pragma: no cover - the failure we guard
        pytest.fail(f"upgraded fixture reports damage: {exc}")
    conn.close()


def test_the_migrated_fixture_accepts_a_backfill(tmp_path):
    """Sizes land on rows that existed long before the columns did."""
    upgraded = tmp_path / "test-data.sqlite"
    shutil.copy(FIXTURE_DB, upgraded)
    conn = sqlite3.connect(upgraded)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    codes = [r[0] for r in conn.execute("SELECT set_code FROM sets LIMIT 5")]
    changed = apply_total_set_sizes(
        conn, [{"code": c, "card_count": 100} for c in codes]
    )

    assert changed == len(codes)
    conn.close()


# ── What the committed fixture carries ──
#
# de-1ov: the fixture had neither column, so every cached set in a --test
# container reported owned_base / total_base as NULL and no test against one
# could reach the populated path at all.  These pin both branches into the
# file, because a fixture that reaches only one of them is the bug.

#: The one cached set the fixture deliberately leaves without a boundary.
#: MTGJSON reports `baseSetSize: 0` for Special Guests and clean_size reads 0
#: as an absence, so the NULL here is real data rather than a hole poked in the
#: file to make a test pass.
FIXTURE_NULL_BASE_SET = "spg"


def _migrated_fixture(tmp_path):
    """The committed fixture, brought forward the way every consumer gets it."""
    migrated = tmp_path / "test-data.sqlite"
    shutil.copy(FIXTURE_DB, migrated)
    conn = sqlite3.connect(migrated)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_the_fixture_carries_sizes_for_every_cached_set(tmp_path):
    """Both columns are populated -- except the one deliberate NULL."""
    conn = _migrated_fixture(tmp_path)
    rows = conn.execute(
        "SELECT set_code, base_set_size, total_set_size FROM sets "
        "WHERE cards_fetched_at IS NOT NULL"
    ).fetchall()
    conn.close()

    assert len(rows) > 1, "the fixture caches no sets to size"
    assert [r["set_code"] for r in rows if r["total_set_size"] is None] == []
    assert [r["set_code"] for r in rows if r["base_set_size"] is None] == [
        FIXTURE_NULL_BASE_SET
    ]


def test_the_fixture_reaches_both_meter_states(tmp_path):
    """One cached set hides the base meter, the rest draw it."""
    conn = _migrated_fixture(tmp_path)
    index = {row["set_code"]: row for row in set_index(conn)}
    conn.close()

    hidden = index[FIXTURE_NULL_BASE_SET]
    assert hidden["owned_base"] is None
    assert hidden["total_base"] is None
    assert hidden["total_all"] > 0, "the all-printings meter is drawn regardless"

    drawn = [row for code, row in index.items() if code != FIXTURE_NULL_BASE_SET]
    assert drawn, "no cached set draws a base meter"
    assert all(row["total_base"] is not None for row in drawn)


def test_the_fixture_reaches_a_boundary_that_is_not_a_count(tmp_path):
    """fin stops at 309 with more than 309 printings at or below it.

    The rule the columns exist for -- a size is a boundary, not a count --
    needs a set where the two differ, or a denominator taken straight from
    base_set_size would pass every test here and still read 309/309 on a
    binder with empty pockets.
    """
    conn = _migrated_fixture(tmp_path)
    index = {row["set_code"]: row for row in set_index(conn)}
    conn.close()

    fin = index["fin"]
    assert fin["base_set_size"] == FIN_BASE_SET_SIZE
    assert fin["total_set_size"] == FIN_TOTAL_SET_SIZE
    assert fin["total_base"] > FIN_BASE_SET_SIZE


def test_the_builder_and_the_fixture_agree_on_the_base_sizes(tmp_path):
    """The constant and the committed binary must not drift apart.

    The fixture is a binary, so the table in build_test_fixture.py is the only
    readable record of what is in it and the only thing a rebuild would write.
    A failure here means one of the two was edited without the other.
    """
    from scripts.build_test_fixture import FIXTURE_BASE_SET_SIZES

    conn = _migrated_fixture(tmp_path)
    stored = {
        row["set_code"]: row["base_set_size"]
        for row in conn.execute(
            "SELECT set_code, base_set_size FROM sets WHERE cards_fetched_at IS NOT NULL"
        )
    }
    conn.close()

    # A size of 0 is an absence, not a size -- see clean_size -- so the sets
    # carrying one are exactly the sets left NULL.
    expected = {
        code.lower(): (size or None) for code, size in FIXTURE_BASE_SET_SIZES.items()
    }
    assert stored == expected
