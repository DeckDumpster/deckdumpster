"""The set index: one row per locally cached set, with completion counts.

Backs `GET /api/sets/index` and the `/sets` page.  The population is
`sets WHERE cards_fetched_at IS NOT NULL` -- every set whose card list has been
pulled down, which is what a binder can actually render.  991 sets qualify at
prod scale, so the answer is unpaginated: a set count is small and bounded,
unlike collection rows.

**The query shape is the whole point.**  Written the obvious way, with the four
completion counts as correlated scalar subqueries over the ~1,000 sets, this
measured 21,460 ms in the design's prod recon and 33,432 ms on the rig below --
the set index page taking twenty to thirty seconds to paint.  The correlated
form re-walks the 7,301 owned rows once per set, roughly 7.2M lookups, to answer
what one pass over `collection` answers.  Aggregating once into CTEs and joining
returns the same 991 rows with the same numbers in **99.8 ms**: 335x, entirely
from query shape.  `tests/test_set_index.py` asserts the plan directly, because
a timing assertion on a fixture-sized database would pass either way.

**Not materialised.**  This repo has that pattern -- `collection_value_history`
plus `collection_rev` plus three triggers -- and it earns its place there because
a growth time series cannot be recomputed from current state.  Per-set counts
can, in 100 ms, and a materialised table here would be a cache to invalidate on
every single one-click add, including the one-click adds the binder exists to
make cheap.  Wrong trade; do not add one.

**The base/all split reads `number_sortable`, not a CAST.**  Base completion
counts *printings at or below the boundary*, not the boundary value: fin has
`base_set_size = 309` but 311 printings there, because `123a`/`123b` sit inside
the base range.  `CAST(collector_number AS INTEGER) <= base_set_size` gets both
of those right and then quietly counts `A-248` as base too, because
`CAST('A-248' AS INTEGER)` is 0 -- the same bug in the same column that
`number_sortable` was added to fix for ordering.  Encoded, the Alchemy namespace
sits a million above every base number and falls out on its own.  This is not
hypothetical at fixture scale: `fin` reads 310 base printings encoded and 311
with a CAST, and the extra one is its single `A-` printing.

**The base total is a filter, not a conditional SUM, and that is worth 6.6x.**
`SUM(CASE WHEN p.number_sortable < ... THEN 1 ELSE 0 END)` over a plain
`GROUP BY set_code` lets SQLite scan the smaller `idx_printings_set`, which does
not carry `number_sortable` -- so it then fetches all 110,018 rows from a 616 MB
table to read one integer, and the CTE costs 662 ms.  With the same predicate in
`WHERE`, the planner picks `idx_printings_set_sortable(set_code, number_sortable,
printing_id)`, which covers it, and the CTE costs 59 ms.  The app never runs
ANALYZE, so there is no `sqlite_stat1` to correct that choice later; the query
has to be written so the covering index is the obvious one.

Measured 2026-08-24 on a rig cloned from the 110,018-printing host catalogue with
the collection grown to prod's 7,301 rows over 4,213 distinct printings.  That
box runs perf work about 1.6x slow, so quote the ratios.
"""

import sqlite3

from mtg_collector.db.collector_number import SUFFIX_ROOM

#: The collection population the completion meters describe.  Only cards in
#: hand: an `ordered` card is not yet a filled pocket in a physical binder, and
#: reconciling a binder against the app is what these numbers are for.
OWNED_STATUS = "owned"

#: A printing is in the base set when its encoded number sorts below the first
#: number above the boundary.  `(boundary + 1) * SUFFIX_ROOM` is that first
#: number's encoding, so every suffix and stamp at the boundary itself
#: (`309a`, `309*`) stays inside, and every other namespace stays outside.
#: NULL `base_set_size` makes this NULL, which is neither true nor false --
#: a set with no stored boundary contributes to no base count at all.
_IN_BASE_SET = f"p.number_sortable < (s.base_set_size + 1) * {SUFFIX_ROOM}"

#: One row per cached set.  Each CTE is a single pass over one table.
INDEX_SQL = f"""
WITH totals AS (
    SELECT set_code, COUNT(*) AS n
    FROM printings
    GROUP BY set_code
),
base_totals AS (
    SELECT p.set_code AS set_code, COUNT(*) AS n
    FROM printings p
    JOIN sets s ON s.set_code = p.set_code
    WHERE {_IN_BASE_SET}
    GROUP BY p.set_code
),
owned AS (
    -- DISTINCT first, then count: a pocket holds a printing, and owning 28
    -- copies of one card does not fill 28 pockets.
    SELECT p.set_code AS set_code,
           COUNT(*) AS n_all,
           SUM(CASE WHEN {_IN_BASE_SET} THEN 1 ELSE 0 END) AS n_base
    FROM (SELECT DISTINCT printing_id FROM collection WHERE status = '{OWNED_STATUS}') held
    JOIN printings p ON p.printing_id = held.printing_id
    JOIN sets s ON s.set_code = p.set_code
    GROUP BY p.set_code
)
SELECT s.set_code,
       s.set_name,
       s.set_type,
       s.released_at,
       s.digital,
       s.base_set_size,
       s.total_set_size,
       CASE WHEN s.base_set_size IS NULL THEN NULL
            ELSE COALESCE(o.n_base, 0) END AS owned_base,
       CASE WHEN s.base_set_size IS NULL THEN NULL
            ELSE COALESCE(b.n, 0) END AS total_base,
       COALESCE(o.n_all, 0) AS owned_all,
       COALESCE(t.n, 0) AS total_all
FROM sets s
LEFT JOIN totals t ON t.set_code = s.set_code
LEFT JOIN base_totals b ON b.set_code = s.set_code
LEFT JOIN owned o ON o.set_code = s.set_code
WHERE s.cards_fetched_at IS NOT NULL
ORDER BY s.released_at IS NULL, s.released_at DESC, s.set_code
"""

#: Column order of a row, and therefore the key order of the JSON object.
COLUMNS = (
    "set_code",
    "set_name",
    "set_type",
    "released_at",
    "digital",
    "base_set_size",
    "total_set_size",
    "owned_base",
    "total_base",
    "owned_all",
    "total_all",
)


def set_index(conn: sqlite3.Connection) -> list[dict]:
    """Every locally cached set, newest release first, with completion counts.

    `owned_base` / `total_base` are NULL exactly when `base_set_size` is -- a
    set no source reports a boundary for has no base section to be a fraction
    of, and reporting 0/0 would render as NaN%.  `owned_all` / `total_all` are
    always numbers: every cached set has a printing count whether or not
    anything knows where its base set ends.
    """
    return [dict(zip(COLUMNS, row)) for row in conn.execute(INDEX_SQL)]
