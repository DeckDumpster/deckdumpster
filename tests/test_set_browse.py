"""The binder contract for /api/set-browse/:set_code.

Every assertion here fails against the endpoint as it was: it returned a bare
array with one row per *copy*, sorted by `CAST(collector_number AS INTEGER)`,
with no qty, no sections and no prices.

The HTTP shape is covered by tests/integration/test_set_browse_api.py; these
run in the fast tier with no container.

To run: uv run pytest tests/test_set_browse.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mtg_collector.cli.crack_pack_server import PageParamError, _parse_set_browse_params
from mtg_collector.db.models import Card, CardRepository, Printing, PrintingRepository
from mtg_collector.db.schema import init_db, refresh_latest_prices
from mtg_collector.db.set_browse import (
    BrowseParams,
    base_ceiling,
    browse_set,
    foil_kinds,
)

NOW = "2025-01-01T00:00:00.000Z"

# A set shaped like fin: a base run that ends at 6, two printings sharing number
# 6 through an `a`/`b` suffix so the boundary is not the count, boosterfun above
# it, and a promo.  base_set_size = 6 with SEVEN printings at or below it.
BASE_SET_SIZE = 6
PRINTINGS = [
    # (collector_number, rarity, finishes, promo, promo_types, expected section)
    ("1", "common", ["nonfoil", "foil"], False, [], "base"),
    ("2", "common", ["nonfoil"], False, [], "base"),
    ("3", "uncommon", ["nonfoil", "foil"], False, [], "base"),
    ("4", "rare", ["nonfoil", "foil"], False, ["surgefoil"], "base"),
    ("5", "mythic", ["nonfoil", "foil"], False, [], "base"),
    ("6a", "common", ["nonfoil"], False, [], "base"),
    ("6b", "common", ["nonfoil"], False, [], "base"),
    ("7", "rare", ["foil"], False, ["boosterfun"], "extended"),
    ("8", "mythic", ["etched"], False, ["serialized"], "extended"),
    ("9", "rare", ["nonfoil", "foil"], True, ["promopack"], "promo"),
]


@pytest.fixture
def db():
    """One set, written through the repositories that own the columns."""
    path = tempfile.mkstemp(suffix=".sqlite")[1]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at,"
        " base_set_size, total_set_size) VALUES ('tst', 'Test Set', '2025-01-01', ?, ?, ?)",
        (NOW, BASE_SET_SIZE, len(PRINTINGS)),
    )
    cards, printings = CardRepository(conn), PrintingRepository(conn)
    for i, (cn, rarity, finishes, promo, promo_types, _section) in enumerate(PRINTINGS):
        cards.upsert(Card(oracle_id=f"oracle-{i}", name=f"Card {i:02d}", type_line="Creature"))
        printings.upsert(Printing(
            printing_id=f"print-{i:02d}",
            oracle_id=f"oracle-{i}",
            set_code="tst",
            collector_number=cn,
            rarity=rarity,
            finishes=finishes,
            promo=promo,
            promo_types=promo_types,
        ))
    conn.commit()
    yield conn
    conn.close()
    Path(path).unlink(missing_ok=True)


def _own(conn, printing_id, finish, copies):
    for _ in range(copies):
        conn.execute(
            "INSERT INTO collection (printing_id, finish, acquired_at, source, status)"
            " VALUES (?, ?, ?, 'manual', 'owned')",
            (printing_id, finish, NOW),
        )
    conn.commit()


def _rows(conn, **kw):
    return browse_set(conn, "tst", BrowseParams(**kw), limit=1000, offset=0)


class TestOneRowPerPrinting:
    """Defect 1: the LEFT JOIN had no GROUP BY, so copies became rows."""

    def test_copies_do_not_become_rows(self, db):
        _own(db, "print-00", "nonfoil", 3)
        _own(db, "print-00", "foil", 2)
        _own(db, "print-01", "nonfoil", 4)

        rows = _rows(db, sections=("base", "extended", "promo"))["rows"]

        assert len(rows) == len(PRINTINGS)
        assert len({r["printing_id"] for r in rows}) == len(PRINTINGS)

    def test_a_wishlist_hit_does_not_multiply_either(self, db):
        """An oracle-level want and a printing-level want both match one row."""
        db.executemany(
            "INSERT INTO wishlist (oracle_id, printing_id, priority, added_at) VALUES (?, ?, ?, ?)",
            [("oracle-0", "print-00", 1, NOW), ("oracle-0", None, 3, NOW)],
        )
        db.commit()

        rows = _rows(db, sections=("base", "extended", "promo"))["rows"]

        assert len(rows) == len(PRINTINGS)
        assert rows[0]["wishlist_id"] is not None
        assert rows[0]["wishlist_priority"] == 1

    def test_qty_counts_copies_and_owned_splits_them_by_finish(self, db):
        _own(db, "print-00", "nonfoil", 3)
        _own(db, "print-00", "foil", 2)

        row = _rows(db)["rows"][0]

        assert row["qty"] == 5
        assert row["owned"] == [{"finish": "nonfoil", "qty": 3}, {"finish": "foil", "qty": 2}]

    def test_owned_carries_an_entry_for_every_pip_the_grid_draws(self, db):
        """Unfilled finishes are present at qty 0 — they are pockets, not gaps."""
        row = _rows(db)["rows"][0]

        assert row["owned"] == [{"finish": "nonfoil", "qty": 0}, {"finish": "foil", "qty": 0}]

    def test_a_finish_held_but_not_catalogued_still_reaches_qty(self, db):
        """print-01 exists in nonfoil only; a foil copy of it must not vanish."""
        _own(db, "print-01", "nonfoil", 1)
        _own(db, "print-01", "foil", 1)

        row = _rows(db)["rows"][1]

        assert row["qty"] == 2
        assert sum(o["qty"] for o in row["owned"]) == row["qty"]

    def test_only_owned_copies_count(self, db):
        db.execute(
            "INSERT INTO collection (printing_id, finish, acquired_at, source, status)"
            " VALUES ('print-00', 'nonfoil', ?, 'manual', 'sold')",
            (NOW,),
        )
        db.commit()

        assert _rows(db)["rows"][0]["qty"] == 0


class TestOrder:
    """The set comes back in binder order, off number_sortable."""

    def test_default_sort_is_collector_number(self, db):
        rows = _rows(db, sections=("base", "extended", "promo"))["rows"]

        assert [r["collector_number"] for r in rows] == [p[0] for p in PRINTINGS]

    def test_the_tiebreak_follows_the_sort_direction(self, db):
        """Both terms invert together or SQLite cannot read the index backwards."""
        page_sql = _captured_page_sql(db, BrowseParams(order="desc"))

        assert "ORDER BY p.number_sortable DESC, p.printing_id DESC" in page_sql

    def test_the_plan_reads_the_order_off_one_index(self, db):
        """idx_printings_set_sortable serves the WHERE, the GROUP BY and the
        ORDER BY together; a temp b-tree for the ordering means it did not."""
        page_sql, params = _captured_page(db, BrowseParams())

        plan = "\n".join(str(r[-1]) for r in db.execute("EXPLAIN QUERY PLAN " + page_sql, params))

        assert "idx_printings_set_sortable" in plan
        assert "TEMP B-TREE FOR ORDER BY" not in plan
        assert "TEMP B-TREE FOR RIGHT PART OF ORDER BY" not in plan


class TestSections:
    """The base/boosterfun boundary is read from base_set_size, never derived."""

    def test_section_comes_from_the_stored_boundary(self, db):
        rows = _rows(db, sections=("base", "extended", "promo"))["rows"]

        assert [r["section"] for r in rows] == [p[5] for p in PRINTINGS]

    def test_suffixed_numbers_inside_the_boundary_are_base(self, db):
        """A size is a boundary, not a count: 6 admits `6a` and `6b` both."""
        rows = _rows(db, sections=("base",))["rows"]

        assert [r["collector_number"] for r in rows] == ["1", "2", "3", "4", "5", "6a", "6b"]
        assert len(rows) == BASE_SET_SIZE + 1

    def test_promos_are_on_by_default(self, db):
        rows = _rows(db)["rows"]

        assert "promo" in {r["section"] for r in rows}
        assert len(rows) == len(PRINTINGS)

    def test_the_default_view_reconciles_with_the_all_printings_meter(self, db):
        """The gap de-epk was filed for: `hob` said 321 and drew 320.

        The meter counts every printing in the set, so a section held back from
        the default made the header disagree with the grid under it by exactly
        the hidden promos.  Both numbers come off the same request, which is
        what makes this a reconciliation view rather than two counts.
        """
        body = _rows(db)

        assert body["total"] == body["total_all"] == len(PRINTINGS)
        assert len(body["rows"]) == body["total_all"]

    def test_a_dismissed_section_leaves_the_grid_and_not_the_meter(self, db):
        """Dismissal is by choice, and the meters still measure the set."""
        body = _rows(db, sections=("base", "extended"))

        assert "promo" not in {r["section"] for r in body["rows"]}
        assert body["total"] == len(PRINTINGS) - 1
        assert body["total_all"] == len(PRINTINGS)

    def test_a_set_with_no_recorded_size_is_one_contiguous_run(self, db):
        """NULL is permanent and legitimate; it is not an empty base set."""
        db.execute("UPDATE sets SET base_set_size = NULL WHERE set_code = 'tst'")
        db.commit()

        body = _rows(db, sections=("base", "extended", "promo"))
        sections = {r["collector_number"]: r["section"] for r in body["rows"]}

        assert sections["8"] == "base"
        assert sections["9"] == "promo"
        assert body["owned_base"] is None
        assert body["total_base"] is None


class TestCompletionCounts:
    """Both meters count printings, and neither moves when the view is filtered."""

    def test_counts_are_printings_not_copies(self, db):
        _own(db, "print-00", "nonfoil", 4)

        body = _rows(db)

        assert body["owned_all"] == 1
        assert body["total_all"] == len(PRINTINGS)

    def test_base_counts_printings_at_or_below_the_boundary(self, db):
        _own(db, "print-00", "nonfoil", 1)
        _own(db, "print-07", "foil", 1)

        body = _rows(db)

        assert body["total_base"] == BASE_SET_SIZE + 1
        assert body["owned_base"] == 1

    @pytest.mark.parametrize("view", [
        {"filter": "need"},
        {"filter": "have"},
        {"q": "Card 00"},
        {"sections": ("base",)},
    ])
    def test_filtering_the_view_does_not_move_the_meters(self, db, view):
        _own(db, "print-00", "nonfoil", 1)
        unfiltered = _rows(db)
        meters = ("owned_base", "total_base", "owned_all", "total_all")

        filtered = _rows(db, **view)

        assert [filtered[k] for k in meters] == [unfiltered[k] for k in meters]

    def test_the_header_reaches_the_client_once(self, db):
        """The set header and the meters describe the result, not the window,
        so later windows omit them rather than carrying a stale copy."""
        first = browse_set(db, "tst", BrowseParams(), limit=2, offset=0)
        second = browse_set(db, "tst", BrowseParams(), limit=2, offset=2)

        assert set(first) > {"rows", "total", "limit", "offset"}
        assert set(second) == {"rows", "total", "limit", "offset"}


class TestFilterAndSearch:
    def test_have_and_need_partition_the_set(self, db):
        _own(db, "print-00", "nonfoil", 1)
        all_sections = ("base", "extended", "promo")

        have = _rows(db, filter="have", sections=all_sections)
        need = _rows(db, filter="need", sections=all_sections)

        assert [r["collector_number"] for r in have["rows"]] == ["1"]
        assert have["total"] + need["total"] == len(PRINTINGS)

    def test_q_searches_names_within_the_set(self, db):
        body = _rows(db, q="Card 03")

        assert [r["name"] for r in body["rows"]] == ["Card 03"]
        assert body["total"] == 1


class TestPaging:
    """Defect 2: a bare array with no limit/offset. fin serialised to 743 KiB."""

    def test_the_envelope_bounds_the_page(self, db):
        body = browse_set(db, "tst", BrowseParams(), limit=3, offset=0)

        assert len(body["rows"]) == 3
        assert (body["limit"], body["offset"]) == (3, 0)
        assert body["total"] == len(PRINTINGS)

    def test_an_offset_walk_repeats_no_printing_and_skips_none(self, db):
        _own(db, "print-00", "nonfoil", 3)
        expected = [r["printing_id"] for r in _rows(db)["rows"]]

        walked, offset = [], 0
        while True:
            page = browse_set(db, "tst", BrowseParams(), limit=2, offset=offset)
            walked += [r["printing_id"] for r in page["rows"]]
            if len(page["rows"]) < 2:
                break
            offset += 2

        assert walked == expected
        assert len(set(walked)) == len(walked)


class TestEnrichment:
    """Defect 3: no price, no ck_url, no layout — the machinery was right there."""

    def test_the_row_carries_what_the_tile_renders(self, db):
        row = _rows(db)["rows"][0]

        assert set(row) >= {
            "printing_id", "set_code", "collector_number", "number_sortable",
            "section", "name", "rarity", "image_uri", "layout", "mana_cost",
            "type_line", "cmc", "frame_effects", "border_color", "full_art",
            "finishes", "foil_kinds", "owned", "qty",
            "wishlist_id", "wishlist_priority", "tcg_price", "ck_price", "ck_url",
        }

    def test_a_printing_is_priced_in_the_finish_it_exists_in(self, db):
        """Not in a copy's finish: the pocket this view exists to show is the
        one you have not filled, and it has no copy to take a finish from."""
        db.executemany(
            "INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at)"
            " VALUES ('tst', ?, 'tcgplayer', ?, ?, ?)",
            [("1", "normal", 4.21, "2025-01-01"), ("1", "foil", 99.0, "2025-01-01"),
             ("8", "foil", 7.5, "2025-01-01")],
        )
        refresh_latest_prices(db)
        db.commit()

        rows = {r["collector_number"]: r for r in _rows(db, sections=("base", "extended"))["rows"]}

        assert rows["1"]["tcg_price"] == "4.21"
        # `8` is etched-only, so there is no nonfoil price to prefer.
        assert rows["8"]["tcg_price"] == "7.5"


class TestFoilKinds:
    """finishes says a foil exists; promo_types says what kind of foil it is."""

    def test_the_foil_kind_survives_into_the_row(self, db):
        rows = {r["collector_number"]: r for r in _rows(db)["rows"]}

        assert rows["4"]["foil_kinds"] == ["surgefoil"]
        assert rows["4"]["finishes"] == ["nonfoil", "foil"]

    @pytest.mark.parametrize("promo_types,expected", [
        ('["surgefoil", "universesbeyond", "ffvii"]', ["surgefoil"]),
        ('["boosterfun"]', []),
        ('["galaxyfoil", "ripplefoil"]', ["galaxyfoil", "ripplefoil"]),
        ('["serialized"]', ["serialized"]),
        ('["textured", "neonink"]', ["textured", "neonink"]),
        ("[]", []),
        (None, []),
    ])
    def test_foil_kinds_reads_promo_types(self, promo_types, expected):
        assert foil_kinds(promo_types) == expected


class TestBaseCeiling:
    def test_the_ceiling_admits_a_whole_suffix_block(self):
        """fin records 309 and has 311 printings at or below it."""
        assert base_ceiling(309) == 30999

    def test_no_recorded_size_has_no_ceiling(self):
        assert base_ceiling(None) is None

    def test_the_ceiling_stops_below_the_next_namespace(self):
        """A-248 and S123 live a whole stride above any base set."""
        from mtg_collector.db.collector_number import number_sortable

        ceiling = base_ceiling(9999)

        assert number_sortable("A-1") > ceiling
        assert number_sortable("S1") > ceiling


class TestParams:
    """An unknown value is a 400. A view that quietly ignored `sort=collector`
    would hand back the wrong order and look like a broken endpoint."""

    def _params(self, **kw):
        return {k: [str(v)] for k, v in kw.items()}

    def test_defaults(self):
        view = _parse_set_browse_params({})

        assert (view.sort, view.order, view.filter) == ("number", "asc", "all")
        assert tuple(view.sections) == ("base", "extended", "promo")
        assert view.q == ""

    @pytest.mark.parametrize("params", [
        {"sort": "collector"},
        {"order": "ascending"},
        {"filter": "owned"},
        {"sections": "base,bogus"},
        {"sections": ","},
    ])
    def test_an_unknown_value_is_rejected(self, params):
        with pytest.raises(PageParamError):
            _parse_set_browse_params(self._params(**params))

    def test_accepted_values(self):
        view = _parse_set_browse_params(self._params(
            sort="price", order="desc", filter="need", sections="base,promo", q=" Ajani ",
        ))

        assert (view.sort, view.order, view.filter) == ("price", "desc", "need")
        assert tuple(view.sections) == ("base", "promo")
        assert view.q == "Ajani"


def _captured_page(conn, view):
    """Run a browse and hand back the page statement it issued."""
    statements = []

    class _Recording:
        def execute(self, sql, params=()):
            statements.append((sql, params))
            return conn.execute(sql, params)

        def __getattr__(self, name):
            return getattr(conn, name)

    browse_set(_Recording(), "tst", view, limit=1000, offset=0)
    return next((sql, params) for sql, params in statements if "ORDER BY" in sql)


def _captured_page_sql(conn, view):
    return _captured_page(conn, view)[0]
