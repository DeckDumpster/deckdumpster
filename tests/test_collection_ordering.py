"""`/api/collection` must sort by a total order (de-3qg).

Every sort column the collection page offers is non-unique, and so is the
`card.name` tiebreak — a card with five printings gives five rows with the
same name. Rows that tie on the whole ORDER BY key come back in whatever
order the query plan happens to produce, which is why paging such a result
drops and duplicates rows.

The load-bearing test is `test_order_key_is_total`: it reads the ORDER BY the
server actually emitted and asserts the key values are distinct across the
response. `test_fixture_ties_on_the_old_key` proves that assertion has teeth —
before each template's row identity was appended to its ORDER BY, every
parametrisation of `test_order_key_is_total` failed on this fixture.
"""

import sqlite3
from collections import Counter

import pytest

from mtg_collector.cli.crack_pack_server import CrackPackHandler
from mtg_collector.db.schema import init_db

# Sort options offered by the collection page (keys of the handler's sort_map).
SORTS = [
    "name", "cmc", "rarity", "set", "color", "qty",
    "collector_number", "date_added", "added", "price",
]

TEMPLATES = ["default", "expand_copies", "card_pairs"]

_NAMES = ["Aa Card", "Bb Card", "Cc Card", "Dd Card"]
_SETS = ["aaa", "bbb", "ccc"]
_PRINTINGS_PER_CARD = 5
_ACQUIRED = "2026-01-02T03:04:05.000Z"
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def _fixture_printings():
    """(index, name, set_code, collector_number, printing_id) for every printing.

    Each card is printed five times across three sets, so cards repeat within
    a set — that makes `p.set_code` ambiguous even combined with `card.name`.
    Collector numbers are '42', '42a', '42b', … : unique per set, but all
    equal under the `CAST(collector_number AS INTEGER)` the sort uses.
    """
    rows = []
    for i, name in enumerate(_NAMES):
        for k in range(_PRINTINGS_PER_CARD):
            idx = i * _PRINTINGS_PER_CARD + k
            set_code = _SETS[k % len(_SETS)]
            collector_number = "42" + _ALPHABET[idx]
            rows.append((i, name, set_code, collector_number, f"printing-{idx}"))
    return rows


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    """A collection where every sort column is one big tie."""
    path = str(tmp_path_factory.mktemp("ordering") / "collection.sqlite")
    conn = sqlite3.connect(path)
    init_db(conn)
    for set_code in _SETS:
        conn.execute(
            "INSERT INTO sets (set_code, set_name, released_at, cards_fetched_at)"
            " VALUES (?, ?, '2020-01-01', '2020-01-01T00:00:00Z')",
            (set_code, f"Set {set_code.upper()}"),
        )
    conn.execute(
        "INSERT INTO decks (id, name, format, created_at, updated_at)"
        " VALUES (1, 'Test Deck', 'commander', ?, ?)",
        (_ACQUIRED, _ACQUIRED),
    )
    for i, name in enumerate(_NAMES):
        conn.execute(
            "INSERT INTO cards (oracle_id, name, type_line, mana_cost, cmc, colors, color_identity)"
            ' VALUES (?, ?, \'Creature — Elf\', \'{G}\', 1.0, \'["G"]\', \'["G"]\')',
            (f"oracle-{i}", name),
        )
    for i, _name, set_code, collector_number, printing_id in _fixture_printings():
        conn.execute(
            "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number,"
            ' rarity, finishes, layout) VALUES (?, ?, ?, ?, \'rare\', \'["nonfoil"]\', \'normal\')',
            (printing_id, f"oracle-{i}", set_code, collector_number),
        )
        # Same price for every printing, so sort=price ties too.
        conn.execute(
            "INSERT INTO latest_prices (set_code, collector_number, source, price_type,"
            " price, observed_at) VALUES (?, ?, 'tcgplayer', 'normal', 1.5, '2026-01-01')",
            (set_code, collector_number),
        )
        cursor = conn.execute(
            "INSERT INTO collection (printing_id, finish, condition, acquired_at, source, status)"
            " VALUES (?, 'nonfoil', 'Near Mint', ?, 'manual', 'owned')",
            (printing_id, _ACQUIRED),
        )
        # Half the copies sit in a deck, so expand=copies exercises its
        # deck_cards join with both matched and unmatched rows.
        if i % 2 == 0:
            conn.execute(
                "INSERT INTO deck_cards (deck_id, printing_id, collection_id, zone, quantity)"
                " VALUES (1, ?, ?, 'mainboard', 1)",
                (printing_id, cursor.lastrowid),
            )
    conn.commit()
    conn.close()
    return path


def _params(template, sort):
    params = {"sort": [sort]}
    if template == "expand_copies":
        params["expand"] = ["copies"]
    elif template == "card_pairs":
        pairs = ",".join(f"{sc}:{cn}" for _i, _n, sc, cn, _p in _fixture_printings())
        params["cards"] = [pairs]
    return params


class _RecordingConnection(sqlite3.Connection):
    """Records every (sql, params) so the test can replay the main query."""

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return super().execute(sql, params)


def _call_collection(db_path, params):
    """Invoke the real handler method; return (rows, sql, sql_params)."""
    calls: list = []

    def _get_conn():
        conn = sqlite3.connect(db_path, factory=_RecordingConnection)
        conn.calls = calls
        conn.row_factory = sqlite3.Row
        return conn

    sent: list = []
    handler = object.__new__(CrackPackHandler)
    handler.generator = None
    handler.db_path = db_path
    handler._get_conn = _get_conn
    handler._send_json = lambda obj, status=200: sent.append((obj, status))

    handler._api_collection(params)
    page, status = sent[0]
    assert status == 200, page
    ordered = [(sql, p) for sql, p in calls if "ORDER BY" in sql]
    assert len(ordered) == 1, f"expected one ordered query, got {len(ordered)}"
    # Page envelope: {rows, total, limit, offset}. The fixture is 20 rows, so
    # the default page holds all of them unless the caller asked for fewer.
    return page["rows"], ordered[0][0], ordered[0][1]


def _order_terms(sql):
    """The ORDER BY expressions of the emitted query, stripped of direction."""
    terms = []
    # The query is paged, so the ORDER BY runs to the LIMIT clause, not the end.
    tail = sql.rsplit("ORDER BY", 1)[1].rsplit("LIMIT", 1)[0]
    for term in tail.split(","):
        term = " ".join(term.split())
        for suffix in (" ASC", " DESC"):
            if term.endswith(suffix):
                term = term[: -len(suffix)]
        terms.append(term)
    return terms


_RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}


def _cast_int(collector_number):
    """SQLite's CAST(text AS INTEGER): the leading integer prefix, else 0."""
    digits = ""
    for ch in collector_number:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


def _key_value(term, row, conn):
    """The value one ORDER BY term produced for one response row."""
    if term == "card.name":
        return row.get("oracle_name") or row["name"]
    if term == "card.cmc":
        return row["cmc"]
    if term.startswith("CASE p.rarity"):
        return _RARITY_ORDER.get(row["rarity"], 4)
    if term == "p.set_code":
        return row["set_code"]
    if term == "card.color_identity":
        return row["color_identity"]
    if term == "qty":
        return row["qty"]
    if term == "CAST(p.collector_number AS INTEGER)":
        return _cast_int(row["collector_number"])
    if term == "c.acquired_at":
        return row["acquired_at"]
    if term == "_lp.price":
        return row["tcg_price"]
    # The sortable price columns resolve to the enrichment expressions rather
    # than _lp, which pins price_type but not source and so can match a card
    # once per source. Each of these is exactly the value the payload carries.
    if term == "_tcg.price":
        return row["tcg_price"]
    if term == "COALESCE(_ck_buy.price, _ck_retail.price)":
        return row["ck_price"]
    if term == "p.printing_id":
        return row["printing_id"]
    if term in ("c.finish", "c.condition", "c.status"):
        return row[term.split(".")[1]]
    if term == "c.order_id":
        return row.get("order_id")
    if term == "c.id":
        return row.get("collection_id")
    if term == "dc.id":
        # Not in the payload; the fixture gives a copy at most one deck_cards row.
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM deck_cards WHERE collection_id = ?",
                (row.get("collection_id"),),
            )
        ]
        assert len(ids) <= 1, "fixture gives each copy at most one deck_cards row"
        return ids[0] if ids else None
    raise AssertionError(f"ORDER BY term not observable in the response: {term!r}")


def _keys(rows, terms, db_path):
    conn = sqlite3.connect(db_path)
    try:
        return [tuple(_key_value(t, row, conn) for t in terms) for row in rows]
    finally:
        conn.close()


_TOTAL = len(_NAMES) * _PRINTINGS_PER_CARD


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("sort", SORTS)
def test_order_key_is_total(db_path, template, sort):
    """No two rows may share an ORDER BY key — otherwise paging is unsafe."""
    rows, sql, _ = _call_collection(db_path, _params(template, sort))
    assert len(rows) == _TOTAL
    keys = _keys(rows, _order_terms(sql), db_path)
    tied = [k for k, n in Counter(keys).items() if n > 1]
    assert not tied, (
        f"{len(keys) - len(set(keys))} rows tie on the full ORDER BY key for "
        f"sort={sort} ({template}); the order is not total: {tied[:3]}"
    )


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("sort", SORTS)
def test_fixture_ties_on_the_old_key(db_path, template, sort):
    """The sort column plus `card.name` really is ambiguous on this fixture.

    Without this, `test_order_key_is_total` could pass on a fixture that has
    no ties at all and prove nothing.
    """
    rows, sql, _ = _call_collection(db_path, _params(template, sort))
    old_key = _order_terms(sql)[:2]
    assert old_key[1] == "card.name", old_key
    keys = _keys(rows, old_key, db_path)
    assert len(set(keys)) < len(keys), (
        f"fixture has no ties for sort={sort} ({template}) — "
        "the totality test would be vacuous"
    )


@pytest.mark.parametrize("template", TEMPLATES)
def test_paging_returns_every_row_exactly_once(db_path, template):
    """Slicing the emitted query into pages must cover the result exactly once.

    A weaker check than `test_order_key_is_total` — SQLite happens to resolve
    ties consistently while the plan is unchanged — but it is the failure the
    total order exists to prevent, so it stays as a regression guard.
    """
    rows, _sql, _p = _call_collection(db_path, _params(template, "cmc"))
    unpaged = [r["printing_id"] for r in rows]

    page = 7
    paged = []
    for offset in range(0, _TOTAL, page):
        window = _params(template, "cmc") | {"limit": [str(page)], "offset": [str(offset)]}
        paged += [r["printing_id"] for r in _call_collection(db_path, window)[0]]

    assert len(rows) == _TOTAL
    assert paged == unpaged
    assert len(paged) == _TOTAL


def test_repeated_query_returns_identical_order(db_path):
    """Two runs of the same query must agree on the order of tied rows."""
    first, _sql, _p = _call_collection(db_path, _params("default", "rarity"))
    second, _sql2, _p2 = _call_collection(db_path, _params("default", "rarity"))
    assert [r["printing_id"] for r in first] == [r["printing_id"] for r in second]
