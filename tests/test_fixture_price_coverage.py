"""The committed fixture must be able to discriminate on price.

`is:unowned` is the only result in the fixture wide enough (7,603 rows) for a
250-row window to be a window rather than the whole answer, so it is the one
place where paging and price ordering meet.  While no unowned printing carried
a price, every row of that result tied at NULL and `sort=price` returned an
identical order ascending and descending — the widest paging path could not be
exercised for the column users sort by most, and a UI scenario that tried it
looked broken when it was the data (de-9tb).

These guard the fixture, not the server: they are the assertions that fail if a
rebuild of tests/fixtures/test-data.sqlite drops the price seeding, which would
quietly return every price-ordering test above to passing for the wrong reason.

To run: uv run pytest tests/test_fixture_price_coverage.py -v
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from mtg_collector.cli.demo_data import DEMO_CARDS
from mtg_collector.db.schema import init_db
from tests.test_collection_totals import _page

FIXTURE_DB = Path(__file__).parent / "fixtures" / "test-data.sqlite"

# The page the collection client actually asks for.
PAGE = 250


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    """A migrated copy of the committed fixture.

    Module-scoped: the copy is ~60 MB and the migration walks several versions,
    and nothing here writes.
    """
    path = tmp_path_factory.mktemp("fixture-prices") / "test-data.sqlite"
    shutil.copy(FIXTURE_DB, path)
    conn = sqlite3.connect(path)
    init_db(conn)
    conn.commit()
    conn.close()
    return str(path)


def _prices(rows, key="tcg_price"):
    return [None if r[key] is None else float(r[key]) for r in rows]


class TestSeededData:
    """What the fixture holds, checked directly."""

    def test_unowned_printings_are_priced(self, fixture_db):
        conn = sqlite3.connect(fixture_db)
        priced = conn.execute(
            "SELECT COUNT(*) FROM printings p JOIN latest_prices lp"
            "  ON lp.set_code = p.set_code AND lp.collector_number = p.collector_number"
            " AND lp.source = 'tcgplayer' AND lp.price_type = 'normal'"
        ).fetchone()[0]
        conn.close()
        assert priced > PAGE * 4, (
            f"only {priced} printings carry a nonfoil TCGplayer price — too few for a "
            "paged price sort to be more than the first window"
        )

    def test_a_price_type_is_served_by_two_sources(self, fixture_db):
        """latest_prices is keyed (set_code, collector_number, source,
        price_type), so a card with both a TCGplayer and a Card Kingdom price at
        the same price_type has two rows there and a join that pins price_type
        but not source matches it twice.  tests/test_collection_totals.py had to
        synthesise that shape because the shared fixture could not show it."""
        conn = sqlite3.connect(fixture_db)
        groups = conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM latest_prices"
            " GROUP BY set_code, collector_number, price_type"
            " HAVING COUNT(DISTINCT source) > 1)"
        ).fetchone()[0]
        conn.close()
        assert groups > PAGE, f"only {groups} printings are priced by two sources"

    def test_some_printings_stay_unpriced(self, fixture_db):
        """The NULL-price render and NULL-sort paths still need rows to walk.
        Foil-only and etched-only printings have no nonfoil price to publish,
        which is where these come from."""
        conn = sqlite3.connect(fixture_db)
        unpriced = conn.execute(
            "SELECT COUNT(*) FROM printings p WHERE NOT EXISTS ("
            "  SELECT 1 FROM latest_prices lp WHERE lp.set_code = p.set_code"
            "   AND lp.collector_number = p.collector_number"
            "   AND lp.source = 'tcgplayer' AND lp.price_type = 'normal')"
        ).fetchone()[0]
        conn.close()
        assert unpriced > 0

    def test_the_demo_collection_is_left_alone(self, fixture_db):
        """Only blb/124 — the price-chart scenario's card — has a price among
        the printings demo data holds.  Everything the owned collection shows,
        including its totals, reads exactly what it read before the unowned
        catalogue was priced."""
        conn = sqlite3.connect(fixture_db)
        held = {(sc, cn) for sc, cn, *_ in DEMO_CARDS}
        priced_and_held = {
            (r[0], r[1])
            for r in conn.execute("SELECT set_code, collector_number FROM latest_prices")
        } & held
        conn.close()
        assert priced_and_held == {("blb", "124")}


class TestPagedPriceSort:
    """The property the seeding exists for, through the real handler."""

    def test_direction_changes_the_first_page(self, fixture_db):
        """The degenerate case: with every row tied at NULL these two were the
        same list."""
        asc = [r["printing_id"] for r in
               _page(fixture_db, q="is:unowned", sort="price", order="asc", limit=PAGE)["rows"]]
        desc = [r["printing_id"] for r in
                _page(fixture_db, q="is:unowned", sort="price", order="desc", limit=PAGE)["rows"]]
        assert len(asc) == len(desc) == PAGE
        assert asc != desc

    def test_a_paged_walk_is_ordered_and_covers_each_row_once(self, fixture_db):
        """Five windows of the widest result in the fixture.  Descending, so the
        walk starts in the priced band rather than in the NULLs SQLite sorts
        first."""
        seen, prices = [], []
        for offset in range(0, PAGE * 5, PAGE):
            body = _page(fixture_db, q="is:unowned", sort="price", order="desc",
                         limit=PAGE, offset=offset)
            assert len(body["rows"]) == PAGE
            seen += [r["printing_id"] for r in body["rows"]]
            prices += _prices(body["rows"])

        assert len(set(seen)) == len(seen), "the price-sorted walk repeated a printing"
        assert None not in prices, "the walk left the priced band — seed more prices"
        assert prices == sorted(prices, reverse=True)
        assert prices[0] > prices[-1], "the whole walk sat on one price"

    def test_the_two_sources_rank_the_catalogue_differently(self, fixture_db):
        """Otherwise `sort=ck_price` could pass while sorting on the TCGplayer
        price."""
        by_tcg = [r["printing_id"] for r in
                  _page(fixture_db, q="is:unowned", sort="tcg_price", order="desc",
                        limit=PAGE)["rows"]]
        by_ck = [r["printing_id"] for r in
                 _page(fixture_db, q="is:unowned", sort="ck_price", order="desc",
                       limit=PAGE)["rows"]]
        assert by_tcg != by_ck
