"""sets.set_type / released_at / digital, and the backfill that repairs them (de-mfe).

`mtg cache all` writes all three for every set it upserts, but a `sets` row is
not evidence it ever ran: `mtg data import` and the TCGCSV sealed importer
create stubs with `INSERT OR IGNORE INTO sets (set_code, set_name)`, and until
de-22j `mtg cache set` skipped a set whose row already existed.  174 of the 192
sets in the committed fixture carry NULL `released_at` because of it.

These tests pin what the backfill writes and what a written date buys: `year:`
matching the set at all, and the /sets index sorting it by date instead of
bucketing it under `released_at IS NULL`.

To run: uv run pytest tests/test_set_metadata.py -v
"""

import sqlite3

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.db.set_backfill import apply_set_metadata
from mtg_collector.db.set_index import set_index
from mtg_collector.search import compile_query, parse_query
from mtg_collector.search.compiler import execute_search
from mtg_collector.services.bulk_import import ScryfallBulkClient

#: Guilds of Ravnica, as Scryfall describes it.
GRN_RELEASED_AT = "2018-10-05"
GRN_SET_TYPE = "expansion"


@pytest.fixture
def db():
    """A stub `sets` row, written exactly the way the two importers write one."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT OR IGNORE INTO sets (set_code, set_name) VALUES ('grn', 'Guilds of Ravnica')"
    )
    conn.commit()
    yield conn
    conn.close()


def _scryfall(code="grn", **overrides):
    """One Scryfall /sets entry, reduced to the fields the backfill reads."""
    entry = {
        "code": code,
        "name": "Guilds of Ravnica",
        "set_type": GRN_SET_TYPE,
        "released_at": GRN_RELEASED_AT,
        "digital": False,
        "card_count": 291,
    }
    entry.update(overrides)
    return [entry]


def _descriptors(conn, set_code="grn"):
    return conn.execute(
        "SELECT set_type, released_at, digital FROM sets WHERE set_code = ?",
        (set_code,),
    ).fetchone()


# ── What lands on a stub row ──


def test_a_stub_row_gets_the_descriptors_it_was_created_without(db):
    apply_set_metadata(db, _scryfall())

    row = _descriptors(db)
    assert row["set_type"] == GRN_SET_TYPE
    assert row["released_at"] == GRN_RELEASED_AT


def test_the_digital_flag_is_stored_as_an_integer(db):
    """The column is INTEGER NOT NULL; Scryfall reports a JSON boolean.

    It is also the one descriptor a stub row cannot be spotted by: DEFAULT 0
    and a paper set's stored 0 are the same byte, so an MTGO-only set stubbed
    by the sealed importer reads as paper until this writes the flag.
    """
    apply_set_metadata(db, _scryfall(digital=True))

    assert _descriptors(db)["digital"] == 1


def test_a_paper_set_keeps_digital_zero(db):
    apply_set_metadata(db, _scryfall(digital=False))

    assert _descriptors(db)["digital"] == 0


def test_counts_come_back_per_column(db):
    """A run that repaired 174 dates and flipped 2 flags is not 176 of anything."""
    changed = apply_set_metadata(db, _scryfall(digital=True))

    assert changed == {"set_type": 1, "released_at": 1, "digital": 1}


# ── NULL is a value, not a gap ──


def test_a_missing_release_date_never_blanks_a_stored_one(db):
    apply_set_metadata(db, _scryfall())
    apply_set_metadata(db, _scryfall(released_at=None))

    assert _descriptors(db)["released_at"] == GRN_RELEASED_AT


def test_an_empty_string_is_not_a_release_date(db):
    """`released_at = ''` passes every IS NULL test while meaning nothing."""
    apply_set_metadata(db, _scryfall(released_at="", set_type=""))

    row = _descriptors(db)
    assert row["released_at"] is None
    assert row["set_type"] is None


def test_a_set_the_payload_omits_is_left_alone(db):
    apply_set_metadata(db, _scryfall(code="dom"))

    row = _descriptors(db)
    assert row["set_type"] is None
    assert row["released_at"] is None


# ── Backfill mechanics: idempotent, batched, UPDATE-only ──


def test_rerunning_the_backfill_writes_nothing(db):
    assert apply_set_metadata(db, _scryfall()) == {
        "set_type": 1, "released_at": 1, "digital": 0
    }
    assert apply_set_metadata(db, _scryfall()) == {
        "set_type": 0, "released_at": 0, "digital": 0
    }


def test_backfill_never_invents_a_set(db):
    """UPDATE only: a set with no local row is not a set this can describe."""
    changed = apply_set_metadata(db, _scryfall(code="zzz"))

    assert changed == {"set_type": 0, "released_at": 0, "digital": 0}
    assert db.execute(
        "SELECT COUNT(*) FROM sets WHERE set_code = 'zzz'"
    ).fetchone()[0] == 0


def test_a_corrected_release_date_is_applied(db):
    """Idempotence is 'no write when unchanged', not 'write once ever'."""
    apply_set_metadata(db, _scryfall(released_at="2018-09-28"))

    assert apply_set_metadata(db, _scryfall())["released_at"] == 1
    assert _descriptors(db)["released_at"] == GRN_RELEASED_AT


def test_an_uppercase_set_code_still_finds_its_row(db):
    """Scryfall codes arrive lowercase, but `sets.set_code` is the only key."""
    apply_set_metadata(db, _scryfall(code="GRN"))

    assert _descriptors(db)["released_at"] == GRN_RELEASED_AT


def test_backfill_batches_cover_every_set(db):
    """A batch size below the input length must not truncate the run."""
    codes = [f"s{n:03d}" for n in range(500)]
    db.executemany(
        "INSERT INTO sets (set_code, set_name) VALUES (?, ?)",
        [(c, c.upper()) for c in codes],
    )
    db.commit()

    changed = apply_set_metadata(
        db,
        [{"code": c, "set_type": "funny", "released_at": GRN_RELEASED_AT} for c in codes],
        batch_size=7,
    )

    assert changed["released_at"] == len(codes)
    assert db.execute(
        "SELECT COUNT(*) FROM sets WHERE released_at = ?", (GRN_RELEASED_AT,)
    ).fetchone()[0] == len(codes)


def test_the_ingest_path_and_the_backfill_read_the_same_fields():
    """`mtg cache all` and the backfill must not disagree about one set object."""
    entry = _scryfall(digital=True)[0]

    model = ScryfallBulkClient().to_set_model(entry)

    assert model.set_type == GRN_SET_TYPE
    assert model.released_at == GRN_RELEASED_AT
    assert model.digital == 1


# ── What a stored date buys ──


def _seed_one_owned_card(conn):
    """One held copy of a GRN card -- enough for `year:` to have a row to match."""
    conn.execute(
        "INSERT INTO cards (oracle_id, name, type_line) "
        "VALUES ('oracle-grn', 'Assassin''s Trophy', 'Instant')"
    )
    conn.execute(
        "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity)"
        " VALUES ('grn-152', 'oracle-grn', 'grn', '152', 'R')"
    )
    conn.execute(
        "INSERT INTO collection (printing_id, finish, status, acquired_at, source)"
        " VALUES ('grn-152', 'nonfoil', 'owned', '2024-03-15T12:34:56.789Z', 'manual')"
    )
    conn.commit()


def _year_search(conn, year):
    """Collection mode: the one place `released_at` is the only set column read.

    `mode="all"` also filters on `s.set_type`, which a stub row is missing too,
    so a miss there would not say which NULL caused it.
    """
    compiled = compile_query(parse_query(f"year:{year}"))
    rows, _ = execute_search(conn, compiled, mode="collection")
    return rows


def test_year_search_cannot_see_a_set_with_no_release_date(db):
    """The bug, stated as a test: `year:` reads released_at and nothing else."""
    _seed_one_owned_card(db)

    assert _year_search(db, 2018) == []


def test_year_search_finds_the_set_once_the_date_is_backfilled(db):
    _seed_one_owned_card(db)

    apply_set_metadata(db, _scryfall())

    assert len(_year_search(db, 2018)) == 1


def test_the_set_index_stops_bucketing_it_under_released_at_is_null(db):
    """`ORDER BY s.released_at IS NULL` sorts every undated set to the bottom."""
    db.execute(
        "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at)"
        " VALUES ('dom', 'Dominaria', '2018-04-27', '2024-01-01T00:00:00Z')"
    )
    db.execute(
        "UPDATE sets SET cards_fetched_at = '2024-01-01T00:00:00Z' WHERE set_code = 'grn'"
    )
    db.commit()
    assert [s["set_code"] for s in set_index(db)] == ["dom", "grn"]

    apply_set_metadata(db, _scryfall())

    assert [s["set_code"] for s in set_index(db)] == ["grn", "dom"]
