"""A set has to come back in binder order, and off an index.

`ORDER BY CAST(collector_number AS INTEGER), collector_number` — what
/api/set-browse does today — puts `A-248` first in every Alchemy-touched set,
because CAST('A-248' AS INTEGER) is 0.  printings.number_sortable is the
encoded integer that fixes it, computed at ingest so the request pays nothing;
idx_printings_set_sortable(set_code, number_sortable, printing_id) is what lets
the grid's ORDER BY come off one index scan instead of a temp b-tree.

The plan assertions mirror tests/test_collection_sort_plan.py, which pinned the
same mechanism for the collection's default sort.

To run: uv run pytest tests/test_number_sortable.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.db.collector_number import NAMESPACE_STRIDE, number_sortable
from mtg_collector.db.models import Card, CardRepository, Printing, PrintingRepository
from mtg_collector.db.schema import init_db, rebuild_number_sortable

# Every collector-number shape in tests/fixtures/test-data.sqlite, plus the one
# the encoding table has no row for.  `fin` is the set the design measured.
FIXTURE_SHAPES = ["1", "99b", "309", "310", "381b", "551a", "551f", "780", "A-248"]


class TestTheEncodingTable:
    """The table in the design, pinned value by value."""

    def test_alchemy_rebalance_sorts_after_every_plain_number(self):
        """The bug that started this: A-248 belongs at the end, not the front."""
        assert number_sortable("A-248") == 1_024_800
        assert number_sortable("A-248") > number_sortable("780")

    def test_plain_numbers_are_the_number_times_a_hundred(self):
        assert number_sortable("123") == 12_300
        assert number_sortable("1") == 100

    def test_lettered_variants_sort_in_letter_order(self):
        assert number_sortable("123a") < number_sortable("123b")
        assert number_sortable("123b") < number_sortable("123c")
        assert number_sortable("123a") == 12_301
        assert number_sortable("123z") == 12_326

    def test_the_prerelease_stamp_sorts_after_the_plain_number(self):
        assert number_sortable("123★") > number_sortable("123")
        assert number_sortable("123★") == 12_350

    def test_the_stamp_sorts_after_every_lettered_variant(self):
        """+50 is above z's +26, so the stamp closes the number's block."""
        assert number_sortable("123★") > number_sortable("123z")

    def test_a_number_and_its_variants_stay_inside_the_next_number(self):
        assert number_sortable("123★") < number_sortable("124")

    def test_starter_numbers_get_their_own_namespace(self):
        assert number_sortable("S123") == 2_012_300
        assert number_sortable("S1") > number_sortable("A-248")

    def test_anything_else_lands_above_every_namespace(self):
        """`A-150e` (lci) matches no shape in the table — an Alchemy rebalance
        that also carries a variant letter.  It is not an error, it just sorts
        last, and printing_id closes the order behind it."""
        assert number_sortable("A-150e") == 3 * NAMESPACE_STRIDE + 15_000
        assert number_sortable("A-150e") > number_sortable("S999")

    def test_the_value_is_a_pure_function_of_the_string(self):
        """Not of a rowid: deployed instances shadow printings with a temp view
        over the shared catalogue, and rowid resolves to NULL through a view."""
        assert number_sortable("A-248") == number_sortable("A-248")
        assert number_sortable(" 123 ") == number_sortable("123")

    def test_numbers_stay_inside_their_namespace_up_to_four_digits(self):
        """The stride bounds n * 100 at 9,999.  MTG's largest set is 779."""
        assert number_sortable("9999") < NAMESPACE_STRIDE

    def test_the_fixture_shapes_sort_the_way_a_binder_is_laid_out(self):
        ordered = sorted(FIXTURE_SHAPES, key=number_sortable)
        assert ordered == [
            "1", "99b", "309", "310", "381b", "551a", "551f", "780", "A-248",
        ]


@pytest.fixture
def set_db():
    """One set, written through the repository that owns printings.

    Deliberately tie-heavy on the sort key: `A-150e` and `A-150f` both land in
    the `other` bucket at the same value, so the ordering falls through to the
    tiebreak the way `fin`'s exotic numbers do.
    """
    fd = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(fd)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, set_type) VALUES ('fin', 'Final Fantasy', 'expansion')"
    )
    conn.execute(
        "INSERT INTO sets (set_code, set_name, set_type) VALUES ('lci', 'Ixalan', 'expansion')"
    )
    cards, printings = CardRepository(conn), PrintingRepository(conn)
    numbers = [str(n) for n in range(1, 600)] + [
        "99b", "381b", "551a", "551f", "551★", "A-248", "S1", "A-150e", "A-150f",
    ]
    for i, cn in enumerate(numbers):
        cards.upsert(Card(oracle_id=f"oracle-{i}", name=f"Card {i:04d}", type_line="Creature"))
        for set_code in ("fin", "lci"):
            printings.upsert(
                Printing(
                    printing_id=f"{set_code}-{i:04d}",
                    oracle_id=f"oracle-{i}",
                    set_code=set_code,
                    collector_number=cn,
                    rarity="rare",
                )
            )
    conn.commit()
    conn.close()
    yield fd
    Path(fd).unlink(missing_ok=True)


#: The binder grid's page query: one set, in collector-number order, windowed.
GRID_SQL = (
    "SELECT p.printing_id, p.collector_number FROM printings p "
    "WHERE p.set_code = ? "
    "ORDER BY p.number_sortable {order}, p.printing_id {order} "
    "LIMIT ? OFFSET ?"
)


def _plan(conn, sql, params):
    return [r[3] for r in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()]


class TestTheGridSortComesOffTheIndex:
    """The assertion this column exists for."""

    @pytest.mark.parametrize("order", ["ASC", "DESC"])
    def test_the_order_by_does_not_sort_the_whole_set(self, set_db, order):
        conn = sqlite3.connect(set_db)
        plan = _plan(conn, GRID_SQL.format(order=order), ("fin", 250, 0))
        conn.close()

        offending = [step for step in plan if "TEMP B-TREE" in step]
        assert not offending, (
            "the whole set is being sorted to hand back one page:\n  " + "\n  ".join(plan)
        )

    def test_the_index_is_what_serves_it(self, set_db):
        """Pin the mechanism, not just the absence of the symptom."""
        conn = sqlite3.connect(set_db)
        plan = _plan(conn, GRID_SQL.format(order="ASC"), ("fin", 250, 0))
        conn.close()

        assert any("idx_printings_set_sortable" in step for step in plan), (
            "the grid's sort is not being served by idx_printings_set_sortable:\n  "
            + "\n  ".join(plan)
        )

    def test_the_index_exists_with_set_code_and_number_sortable_leading(self, set_db):
        conn = sqlite3.connect(set_db)
        columns = [r[2] for r in conn.execute("PRAGMA index_info(idx_printings_set_sortable)")]
        conn.close()
        assert columns[:2] == ["set_code", "number_sortable"]


class TestTheOrderIsBinderOrder:
    """A plan that avoids a sort is worth nothing if the order is wrong."""

    def test_the_alchemy_rebalance_comes_last_not_first(self, set_db):
        conn = sqlite3.connect(set_db)
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT collector_number FROM printings WHERE set_code = 'fin' "
                "ORDER BY number_sortable, printing_id"
            )
        ]
        conn.close()
        assert rows[0] == "1"
        assert rows.index("A-248") > rows.index("599")

    def test_the_old_cast_ordering_is_the_bug_this_replaces(self, set_db):
        """Not an assertion about the new column — evidence that the ordering it
        replaced really does put the Alchemy rebalance in front of card #1.

        Every non-numeric collector number casts to 0 and shares first place,
        so the string tiebreak decides which of them leads; the defect is that
        any of them does."""
        conn = sqlite3.connect(set_db)
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT collector_number FROM printings WHERE set_code = 'fin' "
                "ORDER BY CAST(collector_number AS INTEGER), collector_number"
            )
        ]
        conn.close()
        assert rows.index("A-248") < rows.index("1")

    def test_variants_sit_with_their_number(self, set_db):
        conn = sqlite3.connect(set_db)
        rows = [
            r[0]
            for r in conn.execute(
                "SELECT collector_number FROM printings WHERE set_code = 'fin' "
                "ORDER BY number_sortable, printing_id"
            )
        ]
        conn.close()
        assert rows[rows.index("99") + 1] == "99b"
        assert rows[rows.index("551") + 1 : rows.index("551") + 4] == ["551a", "551f", "551★"]

    def test_paging_the_set_walks_every_row_once(self, set_db):
        """number_sortable is not unique — the printing_id tiebreak is what
        keeps a window boundary from dropping and repeating rows."""
        conn = sqlite3.connect(set_db)
        total = conn.execute(
            "SELECT COUNT(*) FROM printings WHERE set_code = 'fin'"
        ).fetchone()[0]
        seen = []
        for offset in range(0, total, 7):
            seen.extend(
                r[0]
                for r in conn.execute(GRID_SQL.format(order="ASC"), ("fin", 7, offset))
            )
        conn.close()
        assert len(seen) == total
        assert len(set(seen)) == total


class TestPopulatedAtIngest:
    """No work at request time means the column is filled by the writer."""

    def test_upsert_fills_it(self, set_db):
        conn = sqlite3.connect(set_db)
        missing = conn.execute(
            "SELECT COUNT(*) FROM printings WHERE number_sortable IS NULL"
        ).fetchone()[0]
        pinned = conn.execute(
            "SELECT number_sortable FROM printings "
            "WHERE set_code = 'fin' AND collector_number = 'A-248'"
        ).fetchone()[0]
        conn.close()
        assert missing == 0
        assert pinned == 1_024_800

    def test_rebuild_repairs_a_row_written_behind_the_repository(self, set_db):
        conn = sqlite3.connect(set_db)
        conn.execute(
            "UPDATE printings SET number_sortable = NULL WHERE collector_number = 'A-248'"
        )
        conn.commit()
        assert rebuild_number_sortable(conn) == 2  # one per set

        repaired = conn.execute(
            "SELECT DISTINCT number_sortable FROM printings WHERE collector_number = 'A-248'"
        ).fetchall()
        conn.close()
        assert [r[0] for r in repaired] == [1_024_800]

    def test_rebuild_is_idempotent(self, set_db):
        conn = sqlite3.connect(set_db)
        assert rebuild_number_sortable(conn) == 0
        conn.close()


class TestTheMigrationBackfills:
    """The committed fixture is deliberately older than SCHEMA_VERSION."""

    def test_upgrading_an_existing_catalogue_fills_and_indexes_it(self, set_db):
        conn = sqlite3.connect(set_db)
        conn.execute("DROP INDEX idx_printings_set_sortable")
        conn.execute("UPDATE printings SET number_sortable = NULL")
        conn.execute("UPDATE schema_version SET version = 47")
        conn.commit()

        init_db(conn)

        missing = conn.execute(
            "SELECT COUNT(*) FROM printings WHERE number_sortable IS NULL"
        ).fetchone()[0]
        index = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_printings_set_sortable'"
        ).fetchone()
        conn.close()
        assert missing == 0
        assert index is not None
