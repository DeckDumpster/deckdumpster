"""The collection sort must not sort the whole result — on any template.

Reading the name across the join cannot be made fast: the GROUP BY pins the
driving table, so `cards` can never become the outer loop and idx_cards_name can
never satisfy `ORDER BY card.name`, with or without a tiebreak.  Measured at
catalogue scale the plan ended in USE TEMP B-TREE FOR ORDER BY and the page
query took seconds to hand back 250 rows.

The fix is one denormalised name column *per driving table*, each with an index
that also carries that template's row identity, plus a GROUP BY led by the same
column so one index scan serves the grouping and the ordering together and LIMIT
stops it early:

  printings-driven (is:unowned, shared links)
      idx_printings_card_name(card_name, printing_id)          2.3 s -> 8.8 ms
  collection-driven (the owned default, expand=copies)
      idx_collection_card_name(card_name, printing_id, finish,
                               condition, status, order_id)    3.5 s -> 25 ms

Every half is load-bearing — the column, the leading GROUP BY term, and (for the
collection index) the INDEXED BY hint, because with no ANALYZE the planner takes
idx_collection_status instead.  That is what the parametrised plan tests below
pin down.

To run: uv run pytest tests/test_collection_sort_plan.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.db.models import (
    Card,
    CardRepository,
    CollectionEntry,
    CollectionRepository,
    Printing,
    PrintingRepository,
)
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
    collection = CollectionRepository(conn)
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
            # Through the repository, never raw SQL: collection.card_name is
            # filled by the INSERT statement itself, so a hand-written insert
            # leaves the sort key NULL and every name ties.
            collection.add(
                CollectionEntry(
                    id=None,
                    printing_id=f"print-{n:04d}",
                    finish="nonfoil",
                    acquired_at=NOW,
                    source="manual",
                    status="owned",
                )
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

    def test_the_owned_template_does_not_sort_at_all(self, catalog_db):
        """The owned template drives from `collection`, so it needs its own index.

        No index on `printings` can order it — the sort key has to be on the
        driving table. idx_collection_card_name carries the name *and* the
        template's whole row-identity key, so one scan of it answers the
        grouping and the ordering together and LIMIT stops it after a page.
        Measured on 110,018 printings / 121,020 owned copies: 3.5 s -> 25 ms.
        """
        _, rec = _run_collection(catalog_db)
        sql, sql_params = _page_query(rec)
        plan = _plan(rec, sql, sql_params)
        rec.really_close()

        sorts = [
            s for s in plan
            if "TEMP B-TREE FOR GROUP BY" in s or "TEMP B-TREE FOR ORDER BY" in s
        ]
        assert not sorts, "the result is still being sorted:\n  " + "\n  ".join(plan)
        assert any("idx_collection_card_name" in step for step in plan), (
            "the sort is not being served by idx_collection_card_name:\n  "
            + "\n  ".join(plan)
        )

    def test_the_hint_is_what_makes_the_planner_take_it(self, catalog_db):
        """The index alone is not enough, so the hint has to be in the SQL.

        Every one of these queries constrains c.status — the default adds
        `status IN ('owned','ordered')` when the query does not — and with no
        sqlite_stat1 (nothing in this app runs ANALYZE) the planner guesses that
        term is selective and takes idx_collection_status, sorting the whole
        result instead. Measured with the column and index in place but no hint:
        2.3 s, still on idx_collection_status.
        """
        _, rec = _run_collection(catalog_db)
        sql, sql_params = _page_query(rec)
        unhinted = sql.replace(" INDEXED BY idx_collection_card_name", "")
        assert unhinted != sql, "the page query carries no index hint"
        plan = _plan(rec, unhinted, sql_params)
        rec.really_close()

        assert any("TEMP B-TREE FOR GROUP BY" in step for step in plan), (
            "the planner now finds the index unaided; the hint may be removable, "
            "but re-measure at catalogue scale before believing it:\n  "
            + "\n  ".join(plan)
        )

    def test_expand_copies_reads_the_index_too(self, catalog_db):
        """The per-copy template drives from `collection` as well.

        Its row identity ends in c.id/dc.id, which the index cannot carry, so a
        block sort of the trailing terms remains — but the name and printing_id
        prefix comes off the index, which is the part that scales with the
        collection.
        """
        _, rec = _run_collection(catalog_db, expand="copies")
        sql, sql_params = _page_query(rec)
        plan = _plan(rec, sql, sql_params)
        rec.really_close()

        assert any("idx_collection_card_name" in step for step in plan), (
            "the per-copy sort is not being served by the index:\n  "
            + "\n  ".join(plan)
        )

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
    """Both card_name columns are copies, so what keeps them true matters."""

    def test_the_repository_fills_the_collection_copy(self, catalog_db):
        """CollectionRepository.add reads the name off printings in the INSERT."""
        conn = sqlite3.connect(catalog_db)
        blank = conn.execute(
            "SELECT COUNT(*) FROM collection WHERE card_name IS NULL"
        ).fetchone()[0]
        stale = conn.execute(
            "SELECT COUNT(*) FROM collection c JOIN printings p"
            " ON p.printing_id = c.printing_id WHERE c.card_name IS NOT p.card_name"
        ).fetchone()[0]
        conn.close()
        assert (blank, stale) == (0, 0)

    def test_repointing_a_copy_moves_its_sort_key(self, catalog_db):
        """CollectionRepository.update can repoint a copy at another printing.

        The sort key has to follow, or the copy sorts under the card it used to
        be — the one case a write-time fill could get wrong and no rebuild would
        notice, because `printings` never changed.
        """
        from mtg_collector.db.models import CollectionRepository

        conn = sqlite3.connect(catalog_db)
        conn.row_factory = sqlite3.Row
        repo = CollectionRepository(conn)
        entry = repo.get(1)
        assert entry is not None
        # print-0001 is an Ancestral Recall; the last printing is an Elvish Mystic.
        target = f"print-{len(NAMES) * PRINTINGS_PER_NAME:04d}"
        entry.printing_id = target
        assert repo.update(entry)
        conn.commit()

        moved = conn.execute("SELECT card_name FROM collection WHERE id = 1").fetchone()[0]
        conn.close()
        assert moved == NAMES[-1]

    def test_rebuild_repairs_a_rename_on_the_collection_copy(self, catalog_db):
        """A rename reaches `collection` one hop behind `printings`.

        `mtg data refresh-catalog` runs rebuild_card_names() (cards -> printings)
        and then rebuild_collection_card_names() (printings -> collection), so
        the staleness window is the same one printings.card_name already has.
        """
        from mtg_collector.db.schema import (
            rebuild_card_names,
            rebuild_collection_card_names,
        )

        conn = sqlite3.connect(catalog_db)
        conn.execute("UPDATE cards SET name = 'Renamed Recall' WHERE oracle_id = 'oracle-0'")
        conn.commit()
        rebuild_card_names(conn)

        assert rebuild_collection_card_names(conn) == PRINTINGS_PER_NAME
        stale = conn.execute(
            "SELECT COUNT(*) FROM collection c JOIN printings p"
            " ON p.printing_id = c.printing_id WHERE c.card_name IS NOT p.card_name"
        ).fetchone()[0]
        # Idempotent: a second pass has nothing left to correct.
        assert rebuild_collection_card_names(conn) == 0
        conn.close()
        assert stale == 0

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
