"""The default collection sort must not sort the whole result.

/api/collection groups by p.printing_id, which pins printings as the driving
table.  cards can therefore never become the outer loop, so idx_cards_name can
never satisfy `ORDER BY card.name` — with or without a tiebreak.  Measured at
catalogue scale (109,976 rows) the plan ended in USE TEMP B-TREE FOR ORDER BY
and the page query took 2.3 s to hand back 250 rows.

The fix is idx_printings_card_name(card_name, printing_id) plus a GROUP BY led
by the same column, so one index scan serves the grouping and the ordering
together and LIMIT stops it early: 2.3 s -> 8.8 ms.  Both halves are load-
bearing, which is what the parametrised plan test below pins down.

To run: uv run pytest tests/test_collection_sort_plan.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.db.models import Card, CardRepository, Printing, PrintingRepository
from mtg_collector.db.schema import init_db

NOW = "2025-01-01T00:00:00.000Z"

# Deliberately tie-heavy: 5 distinct names across 60 printings, so nearly every
# ordering decision falls through the name to the tiebreak.  A result whose
# names are unique would page correctly even with no tiebreak at all and prove
# nothing.
NAMES = ["Ancestral Recall", "Black Lotus", "Counterspell", "Doom Blade", "Elvish Mystic"]
PRINTINGS_PER_NAME = 12


@pytest.fixture
def catalog_db():
    """A tie-heavy catalogue, written through the repositories that own it."""
    fd = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(fd)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, set_type) VALUES ('tst', 'Test Set', 'core')"
    )
    cards, printings = CardRepository(conn), PrintingRepository(conn)
    n = 0
    for name_idx, name in enumerate(NAMES):
        cards.upsert(Card(oracle_id=f"oracle-{name_idx}", name=name, type_line="Creature"))
        for _ in range(PRINTINGS_PER_NAME):
            n += 1
            printings.upsert(
                Printing(
                    printing_id=f"print-{n:04d}",
                    oracle_id=f"oracle-{name_idx}",
                    set_code="tst",
                    collector_number=str(n),
                    rarity="rare",
                )
            )
            conn.execute(
                "INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
                "VALUES (?, 'nonfoil', ?, 'manual', 'owned')",
                (f"print-{n:04d}", NOW),
            )
    conn.commit()
    conn.close()
    yield fd
    Path(fd).unlink(missing_ok=True)


class _RecordingConnection:
    """A sqlite3.Connection that keeps every statement it was asked to run."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((sql, list(params)))
        return self._conn.execute(sql, params)

    def close(self):
        pass  # the test closes it, after reading what ran

    def really_close(self):
        self._conn.close()


def _run_collection(db_path, **params):
    """Call /api/collection and return (envelope, recorded statements)."""
    from mtg_collector.cli.crack_pack_server import CrackPackHandler

    handler = object.__new__(CrackPackHandler)
    handler.db_path = db_path
    handler.generator = object()  # truthy, never called by this path
    rec = _RecordingConnection(db_path)
    handler._get_conn = lambda: rec
    responses = []
    handler._send_json = lambda obj, status=200: responses.append((status, obj))
    handler._api_collection({k: [str(v)] for k, v in params.items()})
    status, body = responses[-1]
    assert status == 200, body
    return body, rec


def _page_query(rec):
    """The statement that fetched the page — the only one that is windowed."""
    windowed = [(sql, p) for sql, p in rec.statements if "LIMIT ? OFFSET ?" in sql]
    assert len(windowed) == 1, f"expected one page query, got {len(windowed)}"
    return windowed[0]


def _plan(rec, sql, params):
    return [r[3] for r in rec.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()]


class TestNoWholeResultSort:
    """The assertion this work lives or dies by."""

    @pytest.mark.parametrize(
        "params",
        [
            {},                                    # the default sort
            {"sort": "name"},                      # asked for by name
            {"sort": "name", "order": "desc"},     # and backwards
            {"q": "order:name"},                   # through the search compiler
            {"q": "is:unowned"},                   # the LEFT-JOIN template
        ],
        ids=["default", "sort=name", "sort=name-desc", "order:name", "is:unowned"],
    )
    def test_default_sort_plan_has_no_temp_btree_for_order_by(self, catalog_db, params):
        body, rec = _run_collection(catalog_db, **params)
        sql, sql_params = _page_query(rec)
        plan = _plan(rec, sql, sql_params)
        rec.really_close()

        offending = [step for step in plan if "TEMP B-TREE FOR ORDER BY" in step]
        assert not offending, (
            "the whole result is being sorted to hand back one page:\n  "
            + "\n  ".join(plan)
        )

    def test_the_index_is_what_serves_it(self, catalog_db):
        """Pin the mechanism, not just the absence of a symptom.

        This is the template the 4.2 s was measured on: `is:unowned` drives
        from printings, so idx_printings_card_name is reachable and one scan of
        it answers the grouping and the ordering together.
        """
        _, rec = _run_collection(catalog_db, q="is:unowned")
        sql, sql_params = _page_query(rec)
        plan = _plan(rec, sql, sql_params)
        rec.really_close()

        assert any("idx_printings_card_name" in step for step in plan), (
            "the sort is not being served by idx_printings_card_name:\n  "
            + "\n  ".join(plan)
        )
        assert not any("TEMP B-TREE FOR GROUP BY" in step for step in plan), (
            "the sort moved into the grouping instead of going away:\n  "
            + "\n  ".join(plan)
        )

    def test_the_owned_template_sorts_at_most_once(self, catalog_db):
        """The owned template drives from `collection`, so no index on printings
        can serve its ordering — but it must not sort twice.

        It used to pay a temp B-tree for the grouping *and* another for the
        ordering. Leading the grouping with the sort column makes the grouping's
        own sort produce the order too: measured 2.2 s -> 2.0 s at offset 0 and
        3.6 s -> 2.4 s at offset 50,000 on a 100,045-copy collection. Making
        this path index-served needs the same denormalisation on `collection`
        and is filed separately.
        """
        _, rec = _run_collection(catalog_db)
        sql, sql_params = _page_query(rec)
        plan = _plan(rec, sql, sql_params)
        rec.really_close()

        sorts = [s for s in plan if "TEMP B-TREE FOR GROUP BY" in s or "TEMP B-TREE FOR ORDER BY" in s]
        assert len(sorts) <= 1, "the result is being sorted twice:\n  " + "\n  ".join(plan)

    def test_descending_tiebreak_follows_the_sort(self, catalog_db):
        """A DESC sort with ASC tiebreaks cannot be read off one index.

        SQLite can only scan an index backwards when every ORDER BY term
        inverts together, so a pinned-ASC tiebreak silently reinstates the full
        sort — measured 4.3 s against 10 ms.
        """
        _, rec = _run_collection(catalog_db, sort="name", order="desc")
        sql, _ = _page_query(rec)
        rec.really_close()
        order_by = sql[sql.rindex("ORDER BY"):]
        assert " ASC" not in order_by, order_by


class TestPagingStaysCorrect:
    """de-3qg's invariant, which the speed-up must not spend."""

    @pytest.mark.parametrize("limit", [1, 2, 7, 13])
    @pytest.mark.parametrize(
        "params",
        [{}, {"sort": "name", "order": "desc"}, {"q": "is:unowned"}],
        ids=["default", "name-desc", "is:unowned"],
    )
    def test_every_row_appears_exactly_once(self, catalog_db, limit, params):
        """Walk the whole result a window at a time and account for every row.

        112,809 printings share only 34,881 distinct names, so without a total
        order the page boundaries land inside a block of equal names and rows
        are silently dropped and repeated.
        """
        first, rec = _run_collection(catalog_db, limit=limit, offset=0, **params)
        rec.really_close()
        total = first["total"]

        seen = []
        offset = 0
        while offset < total:
            body, rec = _run_collection(catalog_db, limit=limit, offset=offset, **params)
            rec.really_close()
            assert body["total"] == total
            seen.extend(
                (r["printing_id"], r.get("finish"), r.get("status")) for r in body["rows"]
            )
            offset += limit

        assert len(seen) == total, f"walked {len(seen)} rows for a result of {total}"
        assert len(set(seen)) == total, (
            f"{len(seen) - len(set(seen))} row(s) repeated across pages"
        )

    def test_the_order_is_the_same_whether_paged_or_not(self, catalog_db):
        """Paging must not reorder: window N must be the same slice of the whole
        result that an unpaged read would have given."""
        whole, rec = _run_collection(catalog_db, limit=1000, offset=0)
        rec.really_close()
        expected = [r["printing_id"] for r in whole["rows"]]

        walked = []
        for offset in range(0, whole["total"], 7):
            body, rec = _run_collection(catalog_db, limit=7, offset=offset)
            rec.really_close()
            walked.extend(r["printing_id"] for r in body["rows"])

        assert walked == expected

    def test_names_come_back_in_name_order(self, catalog_db):
        """The sort is on the denormalised copy, so it has to agree with the
        column the user actually sees."""
        body, rec = _run_collection(catalog_db, limit=1000)
        rec.really_close()
        names = [r["name"] for r in body["rows"]]
        assert names == sorted(names)


class TestDenormalisedNameStaysInSync:
    """printings.card_name is a copy, so what keeps it true matters."""

    def test_upsert_fills_it_from_cards(self, catalog_db):
        conn = sqlite3.connect(catalog_db)
        stale = conn.execute(
            "SELECT COUNT(*) FROM printings p JOIN cards c ON c.oracle_id = p.oracle_id "
            "WHERE p.card_name IS NOT c.name"
        ).fetchone()[0]
        conn.close()
        assert stale == 0

    def test_rebuild_repairs_an_upstream_rename(self, catalog_db):
        """A rename lands in `cards` and leaves `printings` stale until the
        rebuild that `mtg cache` runs at the end of every pass."""
        from mtg_collector.db.schema import rebuild_card_names

        conn = sqlite3.connect(catalog_db)
        conn.execute("UPDATE cards SET name = 'Renamed Recall' WHERE oracle_id = 'oracle-0'")
        conn.commit()

        stale_before = conn.execute(
            "SELECT COUNT(*) FROM printings p JOIN cards c ON c.oracle_id = p.oracle_id "
            "WHERE p.card_name IS NOT c.name"
        ).fetchone()[0]
        assert stale_before == PRINTINGS_PER_NAME

        assert rebuild_card_names(conn) == PRINTINGS_PER_NAME
        stale_after = conn.execute(
            "SELECT COUNT(*) FROM printings p JOIN cards c ON c.oracle_id = p.oracle_id "
            "WHERE p.card_name IS NOT c.name"
        ).fetchone()[0]
        conn.close()
        assert stale_after == 0
