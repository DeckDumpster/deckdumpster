"""One set as a binder page: every printing, in collector-number order.

`GET /api/set-browse/:set_code` existed before this module and had three
defects, all of them contract rather than query (see de-u1a).  This holds the
repaired shape:

  * **One row per printing, never per copy.**  The old `LEFT JOIN collection`
    had no `GROUP BY`, so a printing held in *n* copies came back *n* times --
    2.41x inflation on `sos` against prod, and a binder that renders the same
    pocket three times.  Copies are counted here (`qty`) and broken out per
    finish (`owned`), which is what a reconciliation view actually needs.
  * **A page envelope**, per the collection-payload convention: `{rows, total,
    limit, offset}`, never a bare array.
  * **Enriched** with the prices and the Card Kingdom link the tile renders.

The completion counts are deliberately computed *before* `q`, `filter` and
`sections` are applied, so the header meters do not move when the view is
filtered.

Nothing here derives the base/boosterfun boundary: it is read from
`sets.base_set_size`, which is stored precisely because it cannot be read off
the treatment columns.  See the comment on `sets` in schema.py.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Sequence

from mtg_collector.db.collector_number import SUFFIX_ROOM
from mtg_collector.db.mtgjson_faces import front_face_uuid_sql

#: Where a printing sits in the binder.  `base` is the numbered run the set was
#: printed with, `extended` the boosterfun treatments above it, `promo` the
#: temporally orphaned extras.
#:
#: All three are on by default, because the header meters are counted over
#: every printing in the set and a section held back by fiat makes them
#: disagree with the grid beneath them -- `hob` reported 321 printings and drew
#: 320, the one missing tile being a bundle promo that no control could ask
#: for (de-epk).  A section is dismissed by the pill that says so, and the
#: meters then stay put on purpose: they measure the set, not the view.
SECTION_BASE = "base"
SECTION_EXTENDED = "extended"
SECTION_PROMO = "promo"
SECTIONS = (SECTION_BASE, SECTION_EXTENDED, SECTION_PROMO)
DEFAULT_SECTIONS = SECTIONS

#: `all` every printing, `have` the filled pockets, `need` the empty ones.
FILTERS = ("all", "have", "need")

#: Sort keys the endpoint accepts.  `number` is the default and the only one a
#: binder pass normally wants; the rest exist for the same reasons /collection
#: has them.  `price` is filled in per request from the `price_sources`
#: setting, so the grid sorts by the number it is showing.
SORT_KEYS = ("number", "name", "rarity", "price", "qty")

_SORT_COLUMNS = {
    "number": "p.number_sortable",
    # p.card_name, not card.name -- the denormalised copy, for the same reason
    # /api/collection sorts on it.
    "name": "p.card_name",
    "rarity": (
        "CASE p.rarity WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1"
        " WHEN 'rare' THEN 2 WHEN 'mythic' THEN 3 ELSE 4 END"
    ),
    "qty": "COALESCE(_own.qty, 0)",
}

#: The two sorts an index on `printings` can serve.  Leading the GROUP BY with
#: one of them lets a single scan do the grouping and the ordering; leading it
#: with anything else just moves the sort into the grouping and gains nothing.
_INDEXED_SORTS = ("number", "name")

#: promo_types values that say *how* a card is foiled rather than what it is.
#: The rule is the `foil` suffix plus these, which are foil and ink treatments
#: that do not carry it.  Labelling is the client's job (`FOIL_KIND_LABELS` in
#: shared-card-tile.js falls back to the raw value), so adding one here is
#: enough to make it a badge.
FOIL_KIND_EXTRAS = frozenset({
    "textured", "doublerainbow", "stepandcompleat", "oilslick", "gilded",
    "neonink", "serialized",
})

# The finish a *printing* is priced and linked in.  _ENRICH_JOINS keys the same
# thing on `c.finish`, the finish of a copy in hand -- which is exactly wrong
# here, because the pocket this endpoint exists to show you is the one you have
# not filled, and an unowned printing has no copy to take a finish from.  A
# printing that exists in nonfoil is priced in nonfoil; one that does not (foil-
# only and etched-only printings, 718 of the 7,645-printing fixture) is priced
# in foil.
#
# `finishes` is a JSON array in a TEXT column, so this is a substring test; no
# other finish value contains "nonfoil".
_HAS_NONFOIL = "p.finishes LIKE '%nonfoil%'"


def _finish_case(nonfoil: str, foil: str) -> str:
    return f"CASE WHEN {_HAS_NONFOIL} THEN '{nonfoil}' ELSE '{foil}' END"


# Copies held, aggregated once for the whole collection and joined in as a
# single row per printing.
#
# The obvious `LEFT JOIN collection c ON c.printing_id = p.printing_id AND
# c.status = 'owned'` fans out -- one row per copy, which is defect 1 -- and
# collapsing it again with COUNT(DISTINCT c.id) costs more than the fan-out
# does.  Worse, the `status` term hands the planner a second index to choose
# between, and with no sqlite_stat1 (nothing in this app runs ANALYZE) it picks
# idx_collection_status and re-scans every owned row once per printing:
# measured 1,141 ms against 25 ms on a 7,300-copy collection.  Aggregating
# first leaves printing_id as the only join term, so the plan does not depend
# on statistics that are not there.
#
# COUNT(*), not COUNT(DISTINCT id): nothing has fanned out yet inside here.
_OWNED_JOIN = """
    LEFT JOIN (
        SELECT printing_id, COUNT(*) AS qty
        FROM collection WHERE status = 'owned' GROUP BY printing_id
    ) _own ON _own.printing_id = p.printing_id
"""

_QTY_SQL = "COALESCE(_own.qty, 0)"

#: latest_prices has PRIMARY KEY (set_code, collector_number, source,
#: price_type), so pinning both makes every price join single-row.
_ENRICH_JOINS = f"""
    LEFT JOIN latest_prices _ck_buy ON _ck_buy.set_code = p.set_code
         AND _ck_buy.collector_number = p.collector_number
         AND _ck_buy.source = 'cardkingdom'
         AND _ck_buy.price_type = {_finish_case('buylist_normal', 'buylist_foil')}
    LEFT JOIN latest_prices _ck_retail ON _ck_retail.set_code = p.set_code
         AND _ck_retail.collector_number = p.collector_number
         AND _ck_retail.source = 'cardkingdom'
         AND _ck_retail.price_type = {_finish_case('normal', 'foil')}
    LEFT JOIN latest_prices _tcg ON _tcg.set_code = p.set_code
         AND _tcg.collector_number = p.collector_number
         AND _tcg.source = 'tcgplayer'
         AND _tcg.price_type = {_finish_case('normal', 'foil')}
    -- printing_id is not unique in mtgjson_printings: one row per face of a
    -- double-faced card, both carrying the same Scryfall id with a different
    -- Card Kingdom link.  Resolve to the front face's uuid so the join stays
    -- single-row and links the pocket the grid draws -- mtgjson_faces holds
    -- the rule, shared with /api/collection and the card detail page.
    LEFT JOIN mtgjson_printings _mp ON _mp.uuid =
         {front_face_uuid_sql('p.printing_id')}
"""

_CK_PRICE_SQL = "COALESCE(_ck_buy.price, _ck_retail.price)"
_TCG_PRICE_SQL = "_tcg.price"

_ENRICH_COLUMNS = f"""
    {_CK_PRICE_SQL} AS ck_price,
    {_TCG_PRICE_SQL} AS tcg_price,
    COALESCE(NULLIF(CASE WHEN {_HAS_NONFOIL} THEN _mp.ck_url ELSE _mp.ck_url_foil END, ''),
             _mp.ck_url, '') AS ck_url
"""

#: Which binder section a printing belongs to, given :base_ceiling.
#:
#: A recorded boundary decides it and nothing else does -- a printing inside the
#: numbered run is base whether or not it carries a promo stamp.  With no
#: recorded boundary the set is one contiguous run rather than an extended-art
#: section whose start we cannot see, so everything that is not a promo is base;
#: that is also the shape of every set printed before boosterfun existed.
SECTION_SQL = f"""
    CASE
        WHEN :base_ceiling IS NOT NULL AND p.number_sortable <= :base_ceiling
            THEN '{SECTION_BASE}'
        WHEN p.promo = 1 THEN '{SECTION_PROMO}'
        WHEN :base_ceiling IS NULL THEN '{SECTION_BASE}'
        ELSE '{SECTION_EXTENDED}'
    END
"""


@dataclass(frozen=True)
class BrowseParams:
    """The view, minus paging.  Validated by the caller before it gets here."""

    sort: str = "number"
    order: str = "asc"
    filter: str = "all"
    sections: Sequence[str] = DEFAULT_SECTIONS
    q: str = ""


def base_ceiling(base_set_size: Optional[int]) -> Optional[int]:
    """The largest `number_sortable` still inside the base set, or None.

    A size is a *boundary*, not a count: `fin` records 309 but has 311
    printings at or below it, because suffixed numbers (`123a`, `123b`) sit
    inside the base range and the prerelease stamp does too.  Encoding the
    boundary as `base_set_size` plus a full suffix block puts all of them on the
    base side, and anything in the Alchemy/Starter/other namespaces -- a whole
    stride above -- outside it.
    """
    if base_set_size is None:
        return None
    return base_set_size * SUFFIX_ROOM + SUFFIX_ROOM - 1


def foil_kinds(promo_types: Optional[str]) -> List[str]:
    """The foil-kind badges for a printing, from its raw promo_types JSON.

    Foil-kind is the third axis and the one most easily lost: `finishes` says a
    foil exists, `promo_types` says what kind of foil it is.  Drop the
    distinction and a surge-foil printing looks identical to its ordinary
    sibling in the grid, which is the reconciliation error the binder exists to
    prevent.
    """
    if not promo_types:
        return []
    return [
        t for t in json.loads(promo_types)
        if t.endswith("foil") or t in FOIL_KIND_EXTRAS
    ]


def browse_set(
    conn: sqlite3.Connection,
    set_code: str,
    view: BrowseParams,
    *,
    limit: int,
    offset: int,
    display_source: str = "tcg",
) -> dict:
    """Build the page envelope for one set.  The caller owns the 404 check."""
    set_row = conn.execute(
        "SELECT set_code, set_name, released_at, base_set_size, total_set_size"
        " FROM sets WHERE set_code = ?",
        (set_code,),
    ).fetchone()

    ceiling = base_ceiling(set_row["base_set_size"])
    display_price_sql = _CK_PRICE_SQL if display_source == "ck" else _TCG_PRICE_SQL
    sort_col = _SORT_COLUMNS.get(view.sort) or display_price_sql
    order_dir = "DESC" if view.order == "desc" else "ASC"

    params = {
        "set_code": set_code,
        "base_ceiling": ceiling,
        "limit": limit,
        "offset": offset,
    }

    where = ["p.set_code = :set_code"]
    if set(view.sections) != set(SECTIONS):
        placeholders = []
        for i, section in enumerate(view.sections):
            key = f"section{i}"
            params[key] = section
            placeholders.append(f":{key}")
        where.append(f"({SECTION_SQL}) IN ({', '.join(placeholders)})")
    if view.q:
        params["q"] = f"%{view.q}%"
        where.append("card.name LIKE :q")

    # A filled pocket or an empty one.  _own is single-row per printing, so
    # this is a WHERE term rather than a HAVING: it filters before the grouping
    # instead of after it, and the count below can reuse the same body.
    if view.filter == "have":
        where.append("_own.qty IS NOT NULL")
    elif view.filter == "need":
        where.append("_own.qty IS NULL")

    # The tiebreak inverts with the sort: SQLite reads an index backwards only
    # when every ORDER BY term does, and printing_id is here to make the order
    # total -- which it is in either direction.  Leading the GROUP BY with the
    # sort column is a no-op semantically (printing_id is the primary key, so it
    # already determines every other column) and is what lets one scan of
    # idx_printings_set_sortable serve the grouping and the ordering together.
    group_cols = ["p.printing_id"]
    if view.sort in _INDEXED_SORTS:
        group_cols.insert(0, sort_col)

    body = f"""
        FROM printings p
        JOIN cards card ON p.oracle_id = card.oracle_id
        {_OWNED_JOIN}
        LEFT JOIN wishlist w ON (
            w.printing_id = p.printing_id
            OR (w.printing_id IS NULL AND w.oracle_id = p.oracle_id)
        ) AND w.fulfilled_at IS NULL
        {_ENRICH_JOINS}
        WHERE {' AND '.join(where)}
        GROUP BY {', '.join(group_cols)}
    """

    page_sql = f"""
        SELECT p.printing_id, p.set_code, p.collector_number, p.number_sortable,
               p.rarity, p.image_uri, p.layout, p.frame_effects, p.border_color,
               p.full_art, p.promo, p.promo_types, p.finishes,
               card.name, card.type_line, card.mana_cost, card.cmc,
               ({SECTION_SQL}) AS section,
               {_QTY_SQL} AS qty,
               MAX(w.id) AS wishlist_id,
               MIN(w.priority) AS wishlist_priority,
               {_ENRICH_COLUMNS}
        {body}
        ORDER BY {sort_col} {order_dir}, p.printing_id {order_dir}
        LIMIT :limit OFFSET :offset
    """
    rows = conn.execute(page_sql, params).fetchall()

    owned = _owned_by_finish(conn, [r["printing_id"] for r in rows if r["qty"]])
    results = [_row_to_card(row, owned.get(row["printing_id"], {})) for row in rows]

    # A short page at offset 0 is the whole result, which is the normal case: a
    # set is bounded, the largest real one is 779 printings, and the front end
    # asks for 1000 in one go.  Counting it again would be a second scan for a
    # number already in hand.
    if len(rows) < limit:
        total = offset + len(rows)
    else:
        total = conn.execute(f"SELECT COUNT(*) FROM (SELECT 1 {body})", params).fetchone()[0]

    payload = {"rows": results, "total": total, "limit": limit, "offset": offset}
    if offset == 0:
        payload["set"] = {
            "set_code": set_row["set_code"],
            "set_name": set_row["set_name"],
            "released_at": set_row["released_at"],
            "base_set_size": set_row["base_set_size"],
            "total_set_size": set_row["total_set_size"],
        }
        payload.update(_completion(conn, set_code, ceiling))
    return payload


def _completion(conn: sqlite3.Connection, set_code: str, ceiling: Optional[int]) -> dict:
    """The two header meters, counted before q/filter/sections are applied.

    Both count printings, never copies: a pocket is filled or it is not, and
    holding four copies does not fill four pockets.  The base pair is None --
    not 0/0 -- for a set no source reports a size for, so the bar is hidden
    rather than rendered as NaN%.
    """
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total_all,
               COUNT(_own.qty) AS owned_all,
               COUNT(CASE WHEN p.number_sortable <= :base_ceiling
                          THEN 1 END) AS total_base,
               COUNT(CASE WHEN p.number_sortable <= :base_ceiling AND _own.qty IS NOT NULL
                          THEN 1 END) AS owned_base
        FROM printings p
        {_OWNED_JOIN}
        WHERE p.set_code = :set_code
        """,
        {"set_code": set_code, "base_ceiling": ceiling},
    ).fetchone()
    return {
        "owned_base": row["owned_base"] if ceiling is not None else None,
        "total_base": row["total_base"] if ceiling is not None else None,
        "owned_all": row["owned_all"],
        "total_all": row["total_all"],
    }


def _owned_by_finish(conn: sqlite3.Connection, printing_ids: List[str]) -> dict:
    """{printing_id: {finish: qty}} for the printings on this page that are held.

    A separate statement rather than a second grouping level in the page query:
    grouping by (printing_id, finish) there would put a printing held in two
    finishes on two rows, and paging a result whose rows are not printings drops
    and duplicates pockets.  It is bound by `limit`, which caps at 1000.
    """
    if not printing_ids:
        return {}
    placeholders = ", ".join("?" * len(printing_ids))
    out: dict = {}
    for row in conn.execute(
        f"SELECT printing_id, finish, COUNT(DISTINCT id) AS qty FROM collection"
        f" WHERE status = 'owned' AND printing_id IN ({placeholders})"
        f" GROUP BY printing_id, finish",
        printing_ids,
    ):
        out.setdefault(row["printing_id"], {})[row["finish"]] = row["qty"]
    return out


def _row_to_card(row: sqlite3.Row, owned_finishes: dict) -> dict:
    """One printing, shaped for shared-card-tile.js.

    `owned` carries an entry per finish the printing exists in -- including the
    empty ones, because that is the pip row the grid draws -- plus any finish
    actually held that the catalogue does not list, so `qty` always equals the
    sum of the entries.
    """
    finishes = json.loads(row["finishes"]) if row["finishes"] else []
    listed = list(finishes) + [f for f in owned_finishes if f not in finishes]
    return {
        "printing_id": row["printing_id"],
        "set_code": row["set_code"],
        "collector_number": row["collector_number"],
        "number_sortable": row["number_sortable"],
        "section": row["section"],
        "name": row["name"],
        "rarity": row["rarity"],
        "image_uri": row["image_uri"],
        "layout": row["layout"] or "normal",
        "mana_cost": row["mana_cost"],
        "type_line": row["type_line"],
        "cmc": row["cmc"],
        "frame_effects": row["frame_effects"],
        "border_color": row["border_color"],
        "full_art": bool(row["full_art"]),
        "promo": bool(row["promo"]),
        "finishes": finishes,
        "foil_kinds": foil_kinds(row["promo_types"]),
        "owned": [{"finish": f, "qty": owned_finishes.get(f, 0)} for f in listed],
        "qty": row["qty"],
        "wishlist_id": row["wishlist_id"],
        "wishlist_priority": row["wishlist_priority"],
        # Prices as strings, the shape every other endpoint here hands the tile.
        "tcg_price": None if row["tcg_price"] is None else str(row["tcg_price"]),
        "ck_price": None if row["ck_price"] is None else str(row["ck_price"]),
        "ck_url": row["ck_url"],
    }
