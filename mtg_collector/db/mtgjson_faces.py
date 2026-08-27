"""Resolving a Scryfall printing_id to one MTGJSON row — the front face.

`mtgjson_printings.printing_id` is not unique, and the primary key is `uuid`.
MTGJSON emits one row per *face* of a multi-face card — transform, modal DFC,
adventure, split — and every face carries the same `identifiers.scryfallId`,
which this schema stores as `printing_id`.  335 of the 7,645 printings in
tests/fixtures/test-data.sqlite are two rows for this reason.

The faces are not interchangeable.  Each carries its own
`purchaseUrls.cardKingdom`, and in 19 of those 335 groups only the front face
has one at all — the back face's is empty, so a lookup that lands on it renders
a card whose Card Kingdom link is gone.  Where both are populated they redirect
to the same Card Kingdom product, so that is the extent of the visible damage;
*which* row a query returns is still not something to leave to the plan.

MTGJSON's `side` names the front: `"a"` for the front face of a multi-face
card, `"b"` / `"c"` / `"d"` for the rest, and absent for a single-faced card.
`data_cmd.import_mtgjson` stores it, and every read keyed on printing_id orders
on it through this module rather than restating the rule.

`uuid` closes the order, and is not decoration.  A database imported before the
`side` column existed has NULL on every row; a total order is what keeps such a
database showing one link per card instead of whichever row the index seek
reached first, and the next `mtg data refresh-catalog` re-import fills `side`
in and the front face wins from then on.

`idx_mtgjson_printing` is `(printing_id, side, uuid)` so the seek lands on the
answer already in order and the ORDER BY costs no sorter -- these subqueries
run once per row of the page they enrich, and
tests/test_set_browse.py::TestOrder::test_the_plan_reads_the_order_off_one_index
fails on a temp b-tree anywhere in that plan.

That index makes a bare `LIMIT 1` return the front face too, and the ORDER BY
is *not* therefore redundant: an index is a plan the planner may abandon, and
"whichever row the seek reached first" is precisely the thing this replaces.
Keep the clause; the index is only what makes it free.
"""

_FRONT_FACE_ORDER = "ORDER BY side, uuid LIMIT 1"


def front_face_uuid_sql(printing_id_expr: str) -> str:
    """A correlated scalar subquery yielding the front face's uuid.

    Join `mtgjson_printings` on this rather than on printing_id: uuid is the
    primary key, so the join is single-row by construction instead of by the
    planner's choice of which duplicate to hand back first.
    """
    return (
        "(SELECT uuid FROM mtgjson_printings"
        f" WHERE printing_id = {printing_id_expr} {_FRONT_FACE_ORDER})"
    )


def front_face_sql(columns: str) -> str:
    """`SELECT <columns>` for the front face of one printing_id, bound as `?`."""
    return (
        f"SELECT {columns} FROM mtgjson_printings"
        f" WHERE printing_id = ? {_FRONT_FACE_ORDER}"
    )


def front_face_bulk_sql(columns: str, placeholders: str) -> str:
    """`SELECT <columns>` for the front face of each of several printing_ids.

    One row per printing_id, so a caller keying a dict on it cannot end up with
    whichever face happened to come last.
    """
    return (
        f"SELECT {columns} FROM mtgjson_printings mp"
        f" WHERE mp.printing_id IN ({placeholders})"
        f" AND mp.uuid = {front_face_uuid_sql('mp.printing_id')}"
    )
