"""Daily (count, tcg_value, ck_value) series for the collection.

Two routes to the same numbers:

  * ``compute_series()`` aggregates the series inside SQLite from ``collection``
    and ``prices``.  It honours an arbitrary search filter, and its cost is
    dominated by reading every price row every held card ever had — which grows
    with the day axis, not with the number of points plotted.
  * ``read_history()`` reads the materialized ``collection_value_history``
    table, which is O(days).

The materialized table exists for the **unfiltered** series only.  A filter
changes which collection rows are summed, and there is no way to materialize one
table per possible filter, so a filtered request must go the computed route.
Nothing about that is a fallback: `_api_collection_growth` branches on whether a
query was supplied, and the two branches are separate code paths, not one path
retrying the other.

``rebuild_history()`` is the bridge: it runs the computed route unfiltered over
full history and stores the result.  Two callers, for the two ways the stored
series goes out of date:

  * the price fetch (`mtg data fetch-prices`, i.e. the ``mtgc-prices`` timer) —
    new observations change what the series is worth on the days it covers, and
    the day axis has advanced;
  * the endpoint itself, on the request that first finds the table stale —
    otherwise a single card added to the collection would leave the chart on the
    slow route until the next 06:00 timer run, which for this app is most of the
    time.

Staleness is decided by ``history_is_current()`` against three recorded facts,
never by a heuristic: the collection revision (see ``collection_rev``), the id of
the last price import, and the last day the stored series covers.
"""

import datetime as _dt
import sqlite3

#: The population the materialized table describes, and the default the endpoint
#: applies when the query carries no `status:` of its own.  One definition: a
#: materialized series that summed a different set of rows than the computed one
#: would be wrong in a way no test of either alone could see.
UNFILTERED_WHERE = "c.status IN ('owned', 'ordered')"

#: Staging tables compute_series() builds.  Dropped before and after each run:
#: the endpoint gets a fresh connection per request, but the price timer reuses
#: the process-wide cached connection, where a leftover would collide.
_TEMP_TABLES = ("pop_t", "keys_t", "carry_t", "grp_iv_t", "price_iv_t", "seg_t")

# Aggregates the whole growth series inside SQLite so only one row per day
# crosses the driver boundary (previously ~1.1M price rows did).
#
# Shape, in stages (each a TEMP table so it is computed exactly once):
#   pop_t     - the filtered population, one row per collection entry.
#   keys_t    - distinct (set_code, collector_number, price_type); rowid = kid.
#   carry_t   - per (key, source), the single most recent price strictly
#               before the window. See "Windowing" below.
#   grp_iv_t  - per key, the cumulative quantity held and the day range that
#               quantity is valid for (SUM/LEAD windows over acquisition days).
#   price_iv_t- per (key, source), each price and the day range it is the
#               most recent observation for. LEAD(observed_at) over the price
#               series IS the forward-fill, expressed declaratively.
#   seg_t     - grp_iv_t x price_iv_t intersected on key and overlapping day
#               range: "this many copies at this price for these days".
# The final statement turns segments into a per-day difference array and
# running-sums it over the day spine, which is O(segments) rather than
# O(groups x days).
#
# Windowing (`?range=` days, 0 = full history)
# -------------------------------------------
# Day 0 is the window start, not the first acquisition. The series is
# cumulative, so the window cannot simply drop everything before it — the
# carried-in position has to be reconstructed at day 0:
#
#   quantity - acquisition day offsets are clamped to >= 0, so every
#              pre-window acquisition collapses onto day 0 and the existing
#              GROUP BY sums them into the day-0 opening quantity.
#   price    - the price in effect at the window start is usually OLDER than
#              the window, so `observed_at >= start` alone would zero out
#              those cards until their next observation. carry_t adds back
#              exactly one row per (key, source): the latest price strictly
#              before the window, given sentinel day -1 so it sorts ahead of
#              every in-window row and then clamps to day 0. Its real date is
#              irrelevant once clamped, which is why only `price` is fetched.
#
# carry_t is a seek (ORDER BY observed_at DESC LIMIT 1 on the unique index),
# so it costs O(keys) regardless of how deep the price history goes; a
# GROUP BY ... MAX(observed_at) formulation would instead scan every
# pre-window row and reintroduce the O(history) cost this change removes.
#
# Days are integer offsets from the window start, not date strings:
# the window sort is the dominant cost and sorting one INTEGER beats sorting
# five TEXT columns by a wide margin. Dates are rebuilt for the 163-ish
# output rows only.
#
# Money is summed as INTEGER cents. Every `prices.price` is exactly two
# decimal places, so `ROUND(qty * price * 100)` is exact and the running sum
# carries no float drift across ~1M deltas.  The materialized table stores the
# same cents for the same reason.

_POP_SQL = """
    CREATE TEMP TABLE pop_t AS
    SELECT p.set_code AS set_code,
           p.collector_number AS cn,
           CASE WHEN c.finish IN ('foil', 'etched') THEN 'foil' ELSE 'normal' END AS price_type,
           substr(c.acquired_at, 1, 10) AS acq_date
    FROM collection c
    JOIN printings p ON c.printing_id = p.printing_id
    JOIN cards card ON p.oracle_id = card.oracle_id
    JOIN sets s ON p.set_code = s.set_code
    LEFT JOIN orders o ON c.order_id = o.id
    LEFT JOIN deck_cards dc ON dc.collection_id = c.id
    LEFT JOIN decks d ON dc.deck_id = d.id
    LEFT JOIN binders b ON c.binder_id = b.id
    {extra_joins_sql}
    WHERE ({where_sql}) AND c.acquired_at IS NOT NULL
    GROUP BY c.id
"""

_GRP_SQL = """
    CREATE TEMP TABLE grp_iv_t AS
    WITH grp AS (
        SELECT k.rowid AS kid,
               MAX(MIN(CAST(julianday(pop_t.acq_date) - julianday(?) AS INTEGER), ?), 0) AS day,
               COUNT(*) AS qty
        FROM pop_t
        JOIN keys_t k ON k.set_code = pop_t.set_code
                     AND k.cn = pop_t.cn
                     AND k.price_type = pop_t.price_type
        GROUP BY kid, day
    )
    SELECT kid,
           day AS from_d,
           LEAD(day) OVER w AS to_d,
           qty,
           SUM(qty) OVER w AS cum
    FROM grp
    WINDOW w AS (PARTITION BY kid ORDER BY day)
"""

# `source` is folded to an integer bit (1 = tcgplayer, 0 = cardkingdom) so the
# window partition is a single INTEGER expression.

# The carried-in price: per (key, source) the latest observation strictly
# before the window start. One index seek per row of `keys_t` x 2 sources --
# the correlated ORDER BY ... DESC LIMIT 1 lets SQLite land on the end of the
# range and step back once, so this does not scan pre-window history.
_CARRY_SQL = """
    CREATE TEMP TABLE carry_t AS
    SELECT kid, src, price FROM (
        SELECT k.rowid AS kid,
               s.src AS src,
               (SELECT pr.price
                  FROM prices pr
                 WHERE pr.set_code = k.set_code
                   AND pr.collector_number = k.cn
                   AND pr.source = s.nm
                   AND pr.price_type = k.price_type
                   AND pr.observed_at < ?
                 ORDER BY pr.observed_at DESC
                 LIMIT 1) AS price
        FROM keys_t k
        CROSS JOIN (SELECT 'tcgplayer' AS nm, 1 AS src
                    UNION ALL SELECT 'cardkingdom', 0) s
    )
    WHERE price IS NOT NULL
"""

# LEAD orders on the raw (possibly -1) day so the carried-in row is
# unambiguously first; only the emitted `from_d` is clamped into the window.
# A carried-in row followed by an observation on day 0 yields the empty
# interval [0, 0), whose +cents/-cents deltas cancel.
_PRICE_SQL = """
    CREATE TEMP TABLE price_iv_t AS
    SELECT kid, src, MAX(from_d, 0) AS from_d,
           LEAD(from_d) OVER (PARTITION BY kid * 2 + src ORDER BY from_d) AS to_d,
           price
    FROM (
        SELECT k.rowid AS kid,
               (pr.source = 'tcgplayer') AS src,
               CAST(julianday(pr.observed_at) - julianday(?) AS INTEGER) AS from_d,
               pr.price AS price
        FROM keys_t k
        JOIN prices pr ON pr.set_code = k.set_code
                      AND pr.collector_number = k.cn
                      AND pr.price_type = k.price_type
        WHERE pr.source IN ('tcgplayer', 'cardkingdom')
          AND pr.observed_at >= ?
        UNION ALL
        SELECT kid, src, -1 AS from_d, price FROM carry_t
    )
"""

_SEG_SQL = """
    CREATE TEMP TABLE seg_t AS
    SELECT pv.src AS src,
           MAX(gi.from_d, pv.from_d) AS s,
           CASE WHEN gi.to_d IS NULL THEN pv.to_d
                WHEN pv.to_d IS NULL THEN gi.to_d
                ELSE MIN(gi.to_d, pv.to_d) END AS e,
           CAST(ROUND(gi.cum * pv.price * 100) AS INTEGER) AS cents
    FROM price_iv_t pv
    JOIN grp_iv_t gi ON gi.kid = pv.kid
                    AND (gi.to_d IS NULL OR pv.from_d < gi.to_d)
                    AND (pv.to_d IS NULL OR gi.from_d < pv.to_d)
"""

_SERIES_SQL = """
    WITH RECURSIVE days(dn) AS (
        SELECT 0 UNION ALL SELECT dn + 1 FROM days WHERE dn < ?
    ),
    delta AS (
        SELECT s AS dn, src, cents FROM seg_t
        UNION ALL
        SELECT e AS dn, src, -cents FROM seg_t WHERE e IS NOT NULL
    ),
    dd AS (
        SELECT dn,
               SUM(CASE WHEN src = 1 THEN cents ELSE 0 END) AS dt,
               SUM(CASE WHEN src = 0 THEN cents ELSE 0 END) AS dc
        FROM delta GROUP BY dn
    ),
    cnt AS (
        SELECT from_d AS dn, SUM(qty) AS q FROM grp_iv_t GROUP BY from_d
    )
    SELECT date(?, '+' || dy.dn || ' day') AS d,
           SUM(COALESCE(cnt.q, 0)) OVER (ORDER BY dy.dn) AS n,
           SUM(COALESCE(dd.dt, 0)) OVER (ORDER BY dy.dn) AS tcg_cents,
           SUM(COALESCE(dd.dc, 0)) OVER (ORDER BY dy.dn) AS ck_cents
    FROM days dy
    LEFT JOIN dd ON dd.dn = dy.dn
    LEFT JOIN cnt ON cnt.dn = dy.dn
    ORDER BY dy.dn
"""

#: The response every route returns for a collection with nothing in it.
EMPTY_SERIES = {
    "dates": [], "counts": [], "tcg_values": [], "ck_values": [], "earliest": None,
}


def _today() -> str:
    """Today, UTC.  `acquired_at` is ISO 8601 UTC, so its first 10 chars are a
    UTC date and the day axis has to be built in the same zone."""
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def end_date(earliest: str) -> str:
    """The last day of the series: today, or the first acquisition if that is
    still in the future."""
    return max(_today(), earliest)


def window_start(earliest: str, end_d: str, range_days: int) -> str:
    """First day of a `range_days`-long window ending at `end_d`.

    Clamped to `earliest`, so asking for more days than the collection has is
    the same as asking for everything rather than padding empty days.
    """
    if range_days <= 0:
        return earliest
    win_start = (
        _dt.date.fromisoformat(end_d) - _dt.timedelta(days=range_days)
    ).isoformat()
    return max(win_start, earliest)


def _drop_temp_tables(conn: sqlite3.Connection):
    for name in _TEMP_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS temp.{name}")


def series_rows(
    conn: sqlite3.Connection,
    *,
    where_sql: str,
    params: list,
    extra_joins_sql: str = "",
    range_days: int = 0,
) -> tuple[str | None, list[tuple]]:
    """Compute the series in SQLite.

    Returns ``(earliest, rows)`` where each row is
    ``(date, cumulative_count, tcg_cents, ck_cents)`` and `earliest` is the first
    acquisition in the whole filtered collection, independent of the window, so
    the UI can size its range pills.  ``(None, [])`` when nothing matches.

    Prices forward-fill: the most recent known price <= D is used, including
    observations from before the window.  Cards with no price on/before D
    contribute 0 to value but still count.
    """
    _drop_temp_tables(conn)
    try:
        conn.execute(
            _POP_SQL.format(extra_joins_sql=extra_joins_sql, where_sql=where_sql),
            params,
        )

        today = _today()
        earliest, end_d = conn.execute(
            "SELECT MIN(acq_date),"
            " CASE WHEN MIN(acq_date) > ? THEN MIN(acq_date) ELSE ? END"
            " FROM pop_t",
            (today, today),
        ).fetchone()
        if earliest is None:
            return None, []

        start_d = window_start(earliest, end_d, range_days)
        end_dn = (
            _dt.date.fromisoformat(end_d) - _dt.date.fromisoformat(start_d)
        ).days

        conn.execute(
            "CREATE TEMP TABLE keys_t AS"
            " SELECT DISTINCT set_code, cn, price_type FROM pop_t"
        )
        conn.execute(_CARRY_SQL, (start_d,))
        conn.execute(_GRP_SQL, (start_d, end_dn))
        conn.execute(_PRICE_SQL, (start_d, start_d))
        conn.execute(_SEG_SQL)
        rows = conn.execute(_SERIES_SQL, (end_dn, start_d)).fetchall()
    finally:
        _drop_temp_tables(conn)

    return earliest, [
        (r["d"], r["n"], r["tcg_cents"], r["ck_cents"]) for r in rows
    ]


def payload(earliest: str | None, rows: list[tuple]) -> dict:
    """Turn ``(earliest, rows)`` into the endpoint's response body."""
    if earliest is None:
        return dict(EMPTY_SERIES)
    return {
        "dates": [r[0] for r in rows],
        "counts": [r[1] for r in rows],
        "tcg_values": [r[2] / 100.0 for r in rows],
        "ck_values": [r[3] / 100.0 for r in rows],
        "earliest": earliest,
    }


def compute_series(conn: sqlite3.Connection, **kwargs) -> dict:
    """The computed route: aggregate the series from `collection` + `prices`."""
    return payload(*series_rows(conn, **kwargs))


# ── The materialized unfiltered series ──


def collection_rev(conn: sqlite3.Connection) -> int:
    """The collection's current revision stamp.

    Maintained by triggers on `collection` (see the DDL in schema.py), because
    the stored series has no other way to learn that a card was added, sold,
    refinished or re-attributed to a different printing.
    """
    row = conn.execute("SELECT rev FROM collection_rev WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError(
            "collection_rev holds no row, so the growth cache cannot tell "
            "whether the collection changed. Run 'mtg db init --force'."
        )
    return row[0]


def price_log_id(conn: sqlite3.Connection) -> int:
    """The id of the last price import.

    Prices live in the shared reference DB and are appended wholesale by
    `import_prices`, which logs exactly one row per run — so this moves if and
    only if the price series the stored history was built from has grown.
    """
    return conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM price_fetch_log"
    ).fetchone()[0]


def history_is_current(conn: sqlite3.Connection) -> bool:
    """Whether `collection_value_history` still describes the live data.

    False when it has never been built, when the collection or the prices moved
    under it, or when the day axis has advanced past the last stored day.
    """
    meta = conn.execute(
        "SELECT collection_rev, price_log_id, earliest, through_d"
        " FROM collection_value_history_meta WHERE id = 1"
    ).fetchone()
    if meta is None:
        return False
    if meta["collection_rev"] != collection_rev(conn):
        return False
    if meta["price_log_id"] != price_log_id(conn):
        return False
    if meta["earliest"] is None:
        # An empty collection has no day axis, so no amount of elapsed time
        # makes "empty" the wrong answer — only a collection change can.
        return True
    return meta["through_d"] == end_date(meta["earliest"])


def rebuild_history(conn: sqlite3.Connection) -> int:
    """Recompute and store the unfiltered full-history series.

    Returns the number of days stored.  Stamps the collection revision and price
    import the build saw, which is what `history_is_current()` later checks.

    The stamps are read *before* the series so a collection edit that lands
    mid-build is recorded as not-yet-included and invalidates on the next read,
    rather than being stamped as included and silently missing.
    """
    from mtg_collector.utils import now_iso

    rev = collection_rev(conn)
    log_id = price_log_id(conn)

    earliest, rows = series_rows(conn, where_sql=UNFILTERED_WHERE, params=[])
    through_d = end_date(earliest) if earliest is not None else None

    conn.execute("DELETE FROM collection_value_history")
    conn.executemany(
        "INSERT INTO collection_value_history (d, n, tcg_cents, ck_cents)"
        " VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.execute("DELETE FROM collection_value_history_meta")
    conn.execute(
        "INSERT INTO collection_value_history_meta"
        " (id, built_at, collection_rev, price_log_id, earliest, through_d)"
        " VALUES (1, ?, ?, ?, ?, ?)",
        (now_iso(), rev, log_id, earliest, through_d),
    )
    conn.commit()
    return len(rows)


def read_history(conn: sqlite3.Connection, range_days: int = 0) -> dict:
    """Serve the unfiltered series from the materialized table — O(days).

    Only valid when `history_is_current()`; the caller rebuilds first otherwise.
    A window is a slice: every point is absolute and the series is cumulative, so
    a windowed response is bit-identical to the tail of the full one.
    """
    meta = conn.execute(
        "SELECT earliest, through_d FROM collection_value_history_meta WHERE id = 1"
    ).fetchone()
    if meta["earliest"] is None:
        return dict(EMPTY_SERIES)

    start_d = window_start(meta["earliest"], meta["through_d"], range_days)
    rows = conn.execute(
        "SELECT d, n, tcg_cents, ck_cents FROM collection_value_history"
        " WHERE d >= ? ORDER BY d",
        (start_d,),
    ).fetchall()
    return payload(
        meta["earliest"],
        [(r["d"], r["n"], r["tcg_cents"], r["ck_cents"]) for r in rows],
    )
