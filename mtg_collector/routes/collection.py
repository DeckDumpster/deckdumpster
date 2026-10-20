"""The collection family (multi-tenancy N3): native FastAPI handlers.

Every ``/api/collection*`` route and the ``/api/search`` alias. The logic lives
in plain functions of ``(get_conn, ...)`` returning a ``Json``; the native
routes below call them, and ``CrackPackHandler`` delegates to the same
functions, so the two cannot drift while the legacy adapter still exists. Query
parameters are read exactly as the legacy server read them (``parse_qs``), so
status codes and error bodies are unchanged.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from mtg_collector.cli.crack_pack_server import (
    _CK_PRICE_SQL,
    _COUNT_SELECT,
    _ENRICH_COLUMNS,
    _ENRICH_JOINS,
    _ENRICH_PRICE_JOINS,
    _NAME,
    _TCG_PRICE_SQL,
    PageParamError,
    _aggregate_body_joins,
    _display_price,
    _keep_join,
    _parse_known_total,
    _parse_page_params,
)
from mtg_collector.db import page_cursor
from mtg_collector.http_cache import (
    CACHE_API,
    compute_etag,
    etag_matches,
    negotiate_gzip,
)
from mtg_collector.tenancy.connection import tenant_connection


@dataclass(frozen=True)
class Json:
    obj: Any
    status: int = 200


def collection_list(get_conn, params: dict):
    """Return aggregated collection data with Scryfall-style search.

    The `q` param accepts full Scryfall query syntax plus collection
    extensions (status:, added:, price:, deck:, binder:, is:wanted, etc.).
    When no status: is in the query, defaults to status:owned.
    """
    from mtg_collector.search import (
        PRICE_EXPR,
        SearchError,
        compile_query,
        parse_query,
    )

    try:
        limit, offset = _parse_page_params(params)
        known_total = _parse_known_total(params)
    except PageParamError as e:
        return Json({"error": str(e)}, 400)

    cursor_token = params.get("cursor", [""])[0].strip()
    if cursor_token and params.get("offset", [""])[0].strip():
        return Json({"error": "cursor and offset are exclusive; send one"}, 400)

    q = params.get("q", [""])[0]
    sort = params.get("sort", [""])[0]
    order = params.get("order", [""])[0]
    expand_copies = params.get("expand", [""])[0] == "copies"

    # Explicit card list: ?cards=set:cn,set:cn,... (shared links)
    cards_param = params.get("cards", [""])[0]
    card_pairs = []
    if cards_param:
        for entry in cards_param.split(","):
            entry = entry.strip()
            if ":" in entry:
                sc, cn = entry.split(":", 1)
                card_pairs.append((sc.lower(), cn))

    conn = get_conn()

    # Parse and compile the Scryfall query
    tz = params.get("tz", [""])[0] or None
    where_sql = "1=1"
    sql_params: list = []
    compiled = None
    if q:
        try:
            ast = parse_query(q)
            compiled = compile_query(ast, tz=tz)
            where_sql = compiled.where_sql
            sql_params = list(compiled.params)
        except SearchError as e:
            return Json({"error": str(e), "position": e.position}, 400)

    # is:unowned flips to the LEFT-JOIN template so cards not in the
    # collection can appear in results.
    include_unowned = bool(compiled and compiled.include_unowned)

    # Status default: owned (unless query has explicit status: filter)
    has_status = compiled and compiled.has_status_filter
    if not has_status and not card_pairs and not include_unowned:
        if where_sql == "1=1":
            where_sql = "c.status IN ('owned', 'ordered')"
        else:
            where_sql = f"c.status IN ('owned', 'ordered') AND ({where_sql})"

    # Explicit card list filter (shared links)
    if card_pairs:
        pair_clauses = []
        for sc, cn in card_pairs:
            pair_clauses.append("(p.set_code = ? AND p.collector_number = ?)")
            sql_params.extend([sc, cn])
        card_filter = f"({' OR '.join(pair_clauses)})"
        where_sql = f"{card_filter} AND ({where_sql})" if where_sql != "1=1" else card_filter

    # The price column the client renders follows the price_sources
    # setting, so sorting, the totals below and the `price:` filter follow
    # it too — otherwise the table would order itself by, and filter itself
    # on, a number it is not showing.
    first_source, display_price_sql, display_price_joins = _display_price(conn)

    # `price:` compiles to a single alias for latest_prices, which the
    # compiler cannot resolve to one row per card on its own: the key is
    # (set_code, collector_number, source, price_type), and it has no
    # `settings` to say which source. Pinning price_type alone matched a
    # card priced by both TCG and Card Kingdom twice, and expand=copies has
    # no GROUP BY to collapse it — 600 owned copies were reported and
    # painted as 1200 (de-fb1). Substituting the displayed price drops the
    # alias entirely: the joins it is built from are single-row by
    # construction, and there is no second definition of "the price" left
    # for a filter to disagree with the column about.
    if compiled and compiled.needs_price_join:
        where_sql = where_sql.replace(PRICE_EXPR, display_price_sql)

    # Sort: use search engine order:/direction: if present, else URL params.
    # No sort_map value is unique, and neither is the card.name tiebreak
    # (~3.2 printings share a name), so every template below closes its
    # ORDER BY with the columns that identify one output row — the GROUP BY
    # key where there is one, c.id/dc.id for the per-copy template. Without
    # that the order is not total and paged responses drop and duplicate rows.
    # _NAME is resolved per template to the copy of the name that lives on
    # that template's *driving* table — p.card_name where printings drives,
    # c.card_name where collection does. Never card.name: reading the name
    # across the join cannot be made fast, because the GROUP BY pins the
    # driving table and cards can therefore never be the outer loop, so
    # idx_cards_name is unreachable for ordering with or without a tiebreak.
    # Both copies are denormalised from cards.name and carry the same value.
    sort_map = {
        "name": _NAME,
        "cmc": "card.cmc",
        "rarity": "CASE p.rarity WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1 WHEN 'rare' THEN 2 WHEN 'mythic' THEN 3 ELSE 4 END",
        "set": "p.set_code",
        "color": "card.color_identity",
        "qty": "qty",
        "collector_number": "CAST(p.collector_number AS INTEGER)",
        "date_added": "c.acquired_at",
        "added": "c.acquired_at",
        # These three are expressions from _ENRICH_COLUMNS, whose joins are
        # unconditional and single-row, so they need no needs_*_join flag.
        #
        # `price` deliberately does NOT use _lp. That join pins price_type
        # but not source, and latest_prices' key is (set_code,
        # collector_number, source, price_type) — so with both a TCG and a
        # Card Kingdom price it matches twice. The GROUP BY templates hide
        # that by collapsing the duplicate (while making which source you
        # sorted by a coin toss), but expand=copies has no GROUP BY, and
        # paging a result with duplicated rows drops and repeats cards.
        # Nothing sent `sort` before the client began paging, so this was
        # unreachable rather than fixed.
        "price": display_price_sql,
        "tcg_price": _TCG_PRICE_SQL,
        "ck_price": _CK_PRICE_SQL,
    }
    if compiled and compiled.order_by:
        sort_col = sort_map.get(compiled.order_by, _NAME)
    else:
        sort_col = sort_map.get(sort, _NAME)
    if compiled and compiled.order_dir == "desc":
        order_dir = "DESC"
    elif order:
        order_dir = "DESC" if order == "desc" else "ASC"
    else:
        order_dir = "ASC"

    sorting_by_name = sort_col == _NAME
    # The ORDER BY terms of the template that ran, in order, without their
    # direction: the sort key a cursor records and the next window seeks past.
    order_exprs: list[str] = []

    def _order_by(name_col: str, *identity_cols: str) -> str:
        """ORDER BY for a template, given its name column and row identity.

        The identity columns follow order_dir rather than being pinned ASC.
        An index can only be read backwards when every term inverts
        together, so `card_name DESC, printing_id ASC` falls back to a
        full sort — measured 4.3 s against 10 ms for `... DESC, ... DESC`.
        The direction of a tiebreak is arbitrary either way; it is there to
        make the order total, and it is equally total in either direction.

        The name is added as a secondary sort only when it is not already
        the primary. Repeating it would break the index prefix for nothing.
        """
        terms = [f"{sort_col.replace(_NAME, name_col)} {order_dir}"]
        if not sorting_by_name:
            terms.append(f"{name_col} {order_dir}")
        terms.extend(f"{col} {order_dir}" for col in identity_cols)
        order_exprs[:] = [t.rsplit(" ", 1)[0] for t in terms]
        return "ORDER BY " + ", ".join(terms)

    def _group_by(name_col: str, *key_cols: str) -> str:
        """GROUP BY for a template, given its name column and identity key.

        When the sort is by name, the sort column leads the grouping. That
        is a no-op semantically — printing_id is the primary key and so
        functionally determines card_name, meaning the finer key groups
        exactly the same rows — but it is what lets one index scan satisfy
        the grouping and the ordering at once. Denormalising without this
        measured no better than not denormalising at all (2.4 s vs 2.7 s);
        with it, 8.8 ms.
        """
        cols = list(key_cols)
        if sorting_by_name:
            cols.insert(0, name_col)
        return "GROUP BY " + ", ".join(cols)

    def _collection_sort_index() -> str:
        """The index hint the collection-driven page query needs, if any.

        idx_collection_card_name carries the owned template's entire ORDER
        BY and GROUP BY, but SQLite will not choose it on its own: every one
        of these queries constrains c.status (the default adds
        `status IN ('owned','ordered')` when the query does not), and with
        **no sqlite_stat1** — nothing in this app runs ANALYZE — the planner
        guesses that IN term is selective and takes idx_collection_status,
        paying a temp B-tree over the whole result instead. Measured on
        110,018 printings / 121,020 owned copies with the column and index
        in place but no hint: 2.3 s, still on idx_collection_status. With
        the hint: 6.6 s -> 28 ms for the first page, 6.1 s -> 2.5 s at
        offset 50,000, 12.5 s -> 50 ms for expand=copies.

        Only when the sort is by name: for any other sort this index orders
        by the wrong thing, and the planner's own choice is the right one.

        **This is not free for every query.** An ordered scan pays for
        itself because LIMIT stops it early; a filter selective enough that
        250 matches are spread across the whole collection makes it walk the
        lot in name order, which is random access into `collection` and
        `printings` where the old plan walked rowid order — `s:lci` measured
        630 ms -> 1.2 s. That is inside the band a filtered search already
        cost (`r:mythic` was 1.1 s before, and is 112 ms now), and the
        alternative on this template is the whole-result sort that made the
        unfiltered page unusable. A unary `+` on the status term instead of
        this hint was measured too: same first page, but it leaves the
        planner free to fall back at depth (6.2 s at offset 50,000, against
        2.5 s here), so it buys a little on the selective-filter case and
        loses the paging case.
        """
        return " INDEXED BY idx_collection_card_name" if sorting_by_name else ""

    # Conditional JOINs from the search engine
    # Note: expand_copies and default templates already include dc/d/b joins.
    # Only the shared-links (card_pairs) template needs them dynamically.
    needs_price_join = compiled and compiled.needs_price_join
    needs_wishlist_join = compiled and compiled.needs_wishlist_join

    def _build_extra_joins(*, has_deck_binder_joins: bool, enrich: str = "full") -> str:
        """enrich: "full" for the page, "prices" for the totals, "none" for the count."""
        joins = []
        if not has_deck_binder_joins:
            if compiled and compiled.needs_deck_join:
                joins.append("LEFT JOIN deck_cards dc ON dc.collection_id = c.id")
                joins.append("LEFT JOIN decks d ON dc.deck_id = d.id")
            if compiled and "b.name" in (compiled.where_sql or ""):
                joins.append("LEFT JOIN binders b ON c.binder_id = b.id")
        if needs_price_join and enrich == "none":
            # A `price:` filter is written in the display-price columns, so
            # the count template has to carry their joins even though it
            # enriches nothing. "full" and "prices" already include them.
            joins.extend(display_price_joins)
        if needs_wishlist_join:
            joins.append(
                "LEFT JOIN wishlist _wl ON _wl.oracle_id = card.oracle_id AND _wl.fulfilled_at IS NULL"
            )
        if enrich == "full":
            joins.extend(_ENRICH_JOINS)
        elif enrich == "prices":
            # The totals need a price per row and nothing else. Dropping the
            # ck_url join drops its correlated scalar subquery, which runs
            # once per row of the whole result: 2.6 s -> 1.0 s on 109,976.
            joins.extend(_ENRICH_PRICE_JOINS)
        return "\n                ".join(joins)

    if card_pairs or include_unowned:
        # LEFT JOIN template: shared-link cards or is:unowned queries
        select_sql = f"""
            SELECT
                card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                card.colors, card.color_identity,
                p.set_code, s.set_name, p.collector_number, p.rarity,
                p.printing_id, p.image_uri, p.artist,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes,
                p.flavor_name,
                p.layout,
                p.face0_mana_cost as face0_mana,
                p.face1_mana_cost as face1_mana,
                c.finish, c.condition, c.status,
                COALESCE(COUNT(DISTINCT c.id), 0) as qty,
                MAX(c.acquired_at) as acquired_at,
                CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as owned,
                c.order_id,
                o.seller_name as order_seller,
                o.order_number as order_number,
                o.order_date as order_date,
                c.purchase_price,
                {_ENRICH_COLUMNS}
        """
        def _body(joins: str, *, copies_only: bool = False, agg_select: str = "") -> str:
            collection_join = "JOIN" if copies_only else "LEFT JOIN"
            keep = _keep_join if not agg_select else _aggregate_body_joins(
                agg_select, where_sql, joins, groups=True
            )
            return f"""
            FROM printings p
            {keep('card', 'JOIN cards card ON p.oracle_id = card.oracle_id')}
            {keep('s', 'JOIN sets s ON p.set_code = s.set_code')}
            {collection_join} collection c ON p.printing_id = c.printing_id
            {keep('o', 'LEFT JOIN orders o ON c.order_id = o.id')}
            {joins}
            WHERE ({where_sql}) /*SEEK_W*/
            {_group_by("p.card_name", "p.printing_id")} /*SEEK_H*/
        """
        agg_qty_sql = "COALESCE(COUNT(DISTINCT c.id), 0)"
        agg_select_sql = f"{agg_qty_sql} as qty, {display_price_sql} as price"
        body_sql = _body(_build_extra_joins(has_deck_binder_joins=False))
        count_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=False, enrich="none"),
            agg_select=_COUNT_SELECT,
        )
        # The sums range over copies, and this is the one template whose
        # rows need not have one: a card you do not own is a row here with
        # qty 0, so it adds 0 to total_qty and 0 to total_value whatever it
        # would have been priced at. Inner-joining the copies drops those
        # rows before the price joins are reached rather than pricing
        # 109,976 of them to add zero. See the aggregates below.
        totals_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=False, enrich="prices"),
            copies_only=True,
            agg_select=agg_select_sql,
        )
        # ...and so `total` cannot be counted off it: the rows it drops are
        # exactly the ones an is:unowned result is made of.
        totals_body_spans_result = False
        order_sql = _order_by("p.card_name", "p.printing_id")
    elif expand_copies:
        # One row per collection entry (for deck builder picker)
        select_sql = f"""
            SELECT
                card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                card.colors, card.color_identity,
                p.set_code, s.set_name, p.collector_number, p.rarity,
                p.printing_id, p.image_uri, p.artist,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes,
                p.flavor_name,
                p.layout,
                p.face0_mana_cost as face0_mana,
                p.face1_mana_cost as face1_mana,
                c.finish, c.condition, c.status,
                c.id as collection_id,
                1 as qty,
                c.acquired_at,
                c.order_id,
                o.seller_name as order_seller,
                o.order_number as order_number,
                o.order_date as order_date,
                c.purchase_price,
                dc.deck_id, dc.zone as deck_zone, c.binder_id,
                d.name as deck_name,
                b.name as binder_name,
                {_ENRICH_COLUMNS}
        """
        def _body(joins: str, *, index_hint: str = "", agg_select: str = "") -> str:
            # groups=False: this template pages one row per deck_cards row,
            # so an aggregate over it has to keep the join that makes them.
            keep = _keep_join if not agg_select else _aggregate_body_joins(
                agg_select, where_sql, joins, groups=False
            )
            return f"""
            FROM collection c{index_hint}
            JOIN printings p ON c.printing_id = p.printing_id
            {keep('card', 'JOIN cards card ON p.oracle_id = card.oracle_id')}
            {keep('s', 'JOIN sets s ON p.set_code = s.set_code')}
            {keep('o', 'LEFT JOIN orders o ON c.order_id = o.id')}
            {keep('dc', 'LEFT JOIN deck_cards dc ON dc.collection_id = c.id')}
            {keep('d', 'LEFT JOIN decks d ON dc.deck_id = d.id')}
            {keep('b', 'LEFT JOIN binders b ON c.binder_id = b.id')}
            {joins}
            WHERE ({where_sql}) /*SEEK_W*/
        """
        agg_qty_sql = "1"
        agg_select_sql = f"{agg_qty_sql} as qty, {display_price_sql} as price"
        body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True),
            index_hint=_collection_sort_index(),
        )
        count_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True, enrich="none"),
            agg_select=_COUNT_SELECT,
        )
        totals_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True, enrich="prices"),
            agg_select=agg_select_sql,
        )
        # No GROUP BY on this template: one row per collection entry, so
        # c.id (plus dc.id, which the deck join can duplicate it by) is what
        # identifies a row.
        order_sql = _order_by("c.card_name", "c.printing_id", "c.id", "dc.id")
        totals_body_spans_result = True
    else:
        # Default: aggregated, one row per (printing, finish, condition, status)
        select_sql = f"""
            SELECT
                card.oracle_id, card.name, card.type_line, card.mana_cost, card.cmc,
                card.colors, card.color_identity,
                p.set_code, s.set_name, p.collector_number, p.rarity,
                p.printing_id, p.image_uri, p.artist,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes,
                p.flavor_name,
                p.layout,
                p.face0_mana_cost as face0_mana,
                p.face1_mana_cost as face1_mana,
                c.finish, c.condition, c.status,
                COUNT(DISTINCT c.id) as qty,
                MAX(c.acquired_at) as acquired_at,
                c.order_id,
                o.seller_name as order_seller,
                o.order_number as order_number,
                o.order_date as order_date,
                c.purchase_price,
                dc.deck_id, dc.zone as deck_zone, c.binder_id,
                d.name as deck_name,
                b.name as binder_name,
                {_ENRICH_COLUMNS}
        """
        # Every key column is read off `collection`, never off `printings`:
        # they are the same values by the join, but only the collection copy
        # is what idx_collection_card_name indexes, and SQLite will not
        # cross the join to prove p.printing_id is c.printing_id.
        def _body(joins: str, *, index_hint: str = "", agg_select: str = "") -> str:
            keep = _keep_join if not agg_select else _aggregate_body_joins(
                agg_select, where_sql, joins, groups=True
            )
            return f"""
            FROM collection c{index_hint}
            JOIN printings p ON c.printing_id = p.printing_id
            {keep('card', 'JOIN cards card ON p.oracle_id = card.oracle_id')}
            {keep('s', 'JOIN sets s ON p.set_code = s.set_code')}
            {keep('o', 'LEFT JOIN orders o ON c.order_id = o.id')}
            {keep('dc', 'LEFT JOIN deck_cards dc ON dc.collection_id = c.id')}
            {keep('d', 'LEFT JOIN decks d ON dc.deck_id = d.id')}
            {keep('b', 'LEFT JOIN binders b ON c.binder_id = b.id')}
            {joins}
            WHERE ({where_sql}) /*SEEK_W*/
            {_group_by("c.card_name", "c.printing_id", "c.finish", "c.condition", "c.status", "c.order_id")} /*SEEK_H*/
        """
        # The hint goes on the page query alone. The count and the totals
        # have no ORDER BY, so for them this index is just a scan of every
        # collection row in an order nothing asked for.
        agg_qty_sql = "COUNT(DISTINCT c.id)"
        agg_select_sql = f"{agg_qty_sql} as qty, {display_price_sql} as price"
        body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True),
            index_hint=_collection_sort_index(),
        )
        count_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True, enrich="none"),
            agg_select=_COUNT_SELECT,
        )
        totals_body_sql = _body(
            _build_extra_joins(has_deck_binder_joins=True, enrich="prices"),
            agg_select=agg_select_sql,
        )
        order_sql = _order_by(
            "c.card_name", "c.printing_id", "c.finish", "c.condition", "c.status", "c.order_id"
        )
        totals_body_spans_result = True

    # order_sql stays per-template: the tiebreak is that template's row
    # identity, and it differs (the GROUP BY key, or c.id/dc.id per copy).
    # It is kept out of body_sql so the COUNT below does not sort.
    #
    # LIMIT/OFFSET are bound parameters, never formatted into the SQL.
    #
    # A cursor replaces OFFSET: the page query seeks past the sort key of the
    # last row the caller saw, so a deep window costs what the first one does.
    # The key is every ORDER BY term, ending in the template's unique row
    # identity, and it rides in the page's own select list as _k0.._kN.
    template = "unowned" if (card_pairs or include_unowned) else "copies" if expand_copies else "owned"
    grouped = template != "copies"
    key_exprs = [agg_qty_sql if e == "qty" else e for e in order_exprs]
    fp = page_cursor.fingerprint(
        {k: v for k, v in sorted(params.items()) if k not in ("limit", "offset", "known_total", "cursor")},
        template, key_exprs, order_dir,
    )
    seek_sql, seek_params = "", []
    seek_in_having = False
    if cursor_token:
        try:
            key, cursor_total = page_cursor.decode(cursor_token, fp, len(key_exprs))
        except page_cursor.CursorError as e:
            conn.close()
            return Json({"error": str(e)}, 400)
        offset = 0
        seek_sql, seek_params = page_cursor.seek(key_exprs, key, order_dir == "DESC")
        # qty and the acquired_at of a group are properties of the group, not
        # of a row, so a WHERE cannot see them; HAVING can.
        seek_in_having = grouped and sort_col in ("qty", "c.acquired_at")
    page_body = body_sql.replace("/*SEEK_W*/", "" if seek_in_having or not seek_sql else f"AND {seek_sql}")
    page_body = page_body.replace("/*SEEK_H*/", f"HAVING {seek_sql}" if seek_in_having else "")
    key_select = ", " + ", ".join(f"{e} AS _k{i}" for i, e in enumerate(key_exprs))
    rows = conn.execute(
        f"{select_sql}{key_select}{page_body}{order_sql} LIMIT ? OFFSET ?",
        [*sql_params, *seek_params, limit, offset],
    ).fetchall()

    # A short page has already answered how big the result is: the query ran
    # out of rows, so the result ends here. That covers every query whose
    # result fits in one page — which is most of them — for no extra query
    # at all. (Not when the page is empty and the offset is past the end:
    # then the offset says nothing about where the result stopped.)
    short_page = len(rows) < limit and (rows or offset == 0 or bool(cursor_token))

    include_unowned = bool(card_pairs) or include_unowned
    results = []
    for row in rows:
        mana_cost = row["mana_cost"]
        if not mana_cost:
            face0 = row["face0_mana"] or ""
            face1 = row["face1_mana"] or ""
            if face0 or face1:
                mana_cost = " // ".join(p for p in [face0, face1] if p)
        card = {
            "oracle_id": row["oracle_id"],
            "name": row["flavor_name"] or row["name"],
            "oracle_name": row["name"] if row["flavor_name"] and row["flavor_name"] != row["name"] else None,
            "type_line": row["type_line"],
            "mana_cost": mana_cost,
            "cmc": row["cmc"],
            "colors": row["colors"],
            "color_identity": row["color_identity"],
            "set_code": row["set_code"],
            "set_name": row["set_name"],
            "collector_number": row["collector_number"],
            "rarity": row["rarity"],
            "printing_id": row["printing_id"],
            "image_uri": row["image_uri"],
            "artist": row["artist"],
            "frame_effects": row["frame_effects"],
            "border_color": row["border_color"],
            "full_art": bool(row["full_art"]),
            "promo": bool(row["promo"]),
            "promo_types": row["promo_types"],
            "finishes": row["finishes"],
            "layout": row["layout"] or "normal",
            "finish": row["finish"],
            "condition": row["condition"],
            "status": row["status"],
            "qty": row["qty"],
            "acquired_at": row["acquired_at"],
            "owned": bool(row["owned"]) if include_unowned else True,
        }
        if "collection_id" in row.keys():
            card["collection_id"] = row["collection_id"]
        # Deck/binder info
        if "deck_id" in row.keys() and row["deck_id"]:
            card["deck_id"] = row["deck_id"]
            card["deck_zone"] = row["deck_zone"]
            card["deck_name"] = row["deck_name"]
        if "binder_id" in row.keys() and row["binder_id"]:
            card["binder_id"] = row["binder_id"]
            card["binder_name"] = row["binder_name"]
        # Order info
        order_id = row["order_id"] if "order_id" in row.keys() else None
        if order_id:
            card["order_id"] = order_id
            card["order_seller"] = row["order_seller"]
            card["order_number"] = row["order_number"]
            card["order_date"] = row["order_date"]
            card["purchase_price"] = row["purchase_price"]
        # Prices and ck_url come from the main query's enrichment joins
        # (_ENRICH_COLUMNS); the JSON payload has always carried prices as
        # strings, so keep formatting them here rather than in SQL.
        card["tcg_price"] = None if row["tcg_price"] is None else str(row["tcg_price"])
        card["ck_price"] = None if row["ck_price"] is None else str(row["ck_price"])
        card["ck_url"] = row["ck_url"]
        results.append(card)

    # total, total_qty and total_value all describe the whole result rather
    # than the page, and none of them can be summed from the page: the client
    # fetches windows as it scrolls, so a page-scoped aggregate would climb
    # as the user scrolled — a collection value that grows while you look at
    # it is worse than none. Priced the same way the table is
    # (display_price_sql), so the status line agrees with the price column
    # beside it.
    #
    # total_qty/total_value are computed on the first window only (de-962).
    # They describe the result, not the window, so every later window used to
    # recompute a number the client already had — measured at 1.0 s of the
    # 1.5 s a scroll fetch cost once the page query itself was fixed. The
    # value on screen still never moves, because the client reads them once
    # and keeps them; the keys are simply absent from later windows rather
    # than being present and stale.
    #
    # `total` is on every window: deck-builder.js pages the card picker until
    # `offset >= total`, so dropping it there would turn its loop into a
    # fixed-cap scan, and a caller that opens a window cold would have no
    # way to learn the size of what it is walking. It is instead the one
    # figure a client can hand back — see `known_total` below.
    totals_in_hand = short_page and offset == 0
    price_key = "ck_price" if first_source == "ck" else "tcg_price"
    aggregates = {}

    if cursor_token:
        # The cursor carried the total from the window that issued it.
        total = cursor_total
    elif totals_in_hand:
        # The page is the whole result, so the rows in hand are the answer.
        total = len(results)
        aggregates["total_qty"] = sum(c.get("qty") or 0 for c in results)
        # float() here and on both SQL paths, so the key's JSON type does
        # not depend on what the result held. Python sums an empty result to
        # an integer 0, and SQLite's COALESCE(SUM(...), 0) returns one when
        # no row carried a price; without this, those responses send `0`
        # where every other response sends `0.0`.
        aggregates["total_value"] = round(float(sum(
            float(c[price_key] or 0) * (c.get("qty") or 0) for c in results
        )), 2)
    elif offset == 0 and totals_body_spans_result:
        # One scan for all three. Counting and summing separately walked the
        # same grouped body twice: 1.4 s against 1.0 s for this, same answer.
        # Still true for the templates that drive from `collection`, where
        # the totals body has a row per result row: re-measured at 792 ms
        # combined against 1,242 ms split, on 15,045 copies.
        agg = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(qty), 0), COALESCE(SUM(qty * price), 0) FROM ("
            f"SELECT {agg_select_sql} {totals_body_sql})",
            sql_params,
        ).fetchone()
        total = agg[0]
        aggregates["total_qty"] = agg[1]
        aggregates["total_value"] = round(float(agg[2]), 2)
    elif offset == 0:
        # The is:unowned template's totals body ranges over copies, not over
        # result rows, so it cannot also answer `total` — the rows it drops
        # are exactly the ones the query is about. Two statements, and both
        # are cheaper than the one they replace: the sums no longer price
        # 109,976 rows to add zero, and the count carries no price joins.
        # Measured on 109,976 rows: 7,271 ms combined against 2,515 ms for
        # the pair, of which the sums are under a millisecond.
        agg = conn.execute(
            f"SELECT COALESCE(SUM(qty), 0), COALESCE(SUM(qty * price), 0) FROM ("
            f"SELECT {agg_select_sql} {totals_body_sql})",
            sql_params,
        ).fetchone()
        aggregates["total_qty"] = agg[0]
        aggregates["total_value"] = round(float(agg[1]), 2)
        total = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {_COUNT_SELECT} {count_body_sql})", sql_params
        ).fetchone()[0]
    elif short_page:
        total = offset + len(rows)
    elif known_total is not None:
        # The caller already has the count and sent it back, so nothing is
        # counted (de-j9b). Only this branch honours it: the three above
        # each get the number free from work this request is doing anyway —
        # window 0's single scan, or a short page that ends the walk — and a
        # count this request derived beats one it was told.
        total = known_total
    else:
        # Count the body, which carries the GROUP BY and so counts groups,
        # matching what the page returns. The enrichment joins are left out:
        # a COUNT has no columns to enrich, and each of them matches at most
        # one row, so they cannot change the count either.
        total = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {_COUNT_SELECT} {count_body_sql})", sql_params
        ).fetchone()[0]

    conn.close()
    # Present whenever a full page ended the window; absent once the result
    # has run out. Offset callers get one too, so they can switch mid-walk.
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = page_cursor.encode(
            fp, [last[f"_k{i}"] for i in range(len(key_exprs))], total
        )
    return Json(
        {
            "rows": results,
            "total": total,
            **aggregates,
            "limit": limit,
            "offset": offset,
            "next_cursor": next_cursor,
        }
    )


def collection_growth(get_conn, params: dict):
    """Return daily (count, tcg_value, ck_value) series for the filtered collection.

    Mirrors the search-filter parsing in `/api/collection`. A query is
    aggregated day by day inside SQLite; the *unfiltered* series is instead
    read out of the materialized `collection_value_history` table, which is
    O(days) rather than O(price rows the collection has ever had).

    The two are separate branches on "was a query supplied?", not a fast path
    that falls back — there is one table and a filter would need a different
    one, so a filtered request never consults it and never has a miss to
    recover from. The unfiltered branch rebuilds the table when it is stale
    and then reads it, so the answer always comes from freshly-valid data.

    `?range=` is the window length in days (0 / absent = full history). The
    window is the last `range` days ending today; it is clamped to the first
    acquisition, so asking for more days than the collection has is the same
    as asking for everything. The series is cumulative and every point is
    absolute, so a windowed response is bit-identical to the corresponding
    slice of the full-history response — which is also what lets the stored
    full history serve a windowed request by slicing.

    Prices forward-fill: the most recent known price <= D is used, including
    observations from before the window. Cards with no price on/before D
    contribute 0 to value but still count.

    Response: {"dates": ["YYYY-MM-DD", ...], "counts": [...],
               "tcg_values": [...], "ck_values": [...], "earliest": "..."}
    `earliest` is the first acquisition in the whole filtered collection,
    independent of the window, so the UI can size its range pills.
    """
    from mtg_collector.db import growth
    from mtg_collector.search import (
        PRICE_EXPR,
        SearchError,
        compile_query,
        parse_query,
    )

    # Stripped, so a query bar holding nothing but spaces is the unfiltered
    # case it renders as rather than a filter that happens to match all.
    q = params.get("q", [""])[0].strip()
    tz = params.get("tz", [""])[0] or None
    range_days = int(params.get("range", ["0"])[0] or 0)

    where_sql = "1=1"
    sql_params: list = []
    compiled = None
    if q:
        try:
            ast = parse_query(q)
            compiled = compile_query(ast, tz=tz)
            where_sql = compiled.where_sql
            sql_params = list(compiled.params)
        except SearchError as e:
            return Json({"error": str(e), "position": e.position}, 400)

    # is:unowned makes no sense for a growth chart — ignore.
    if compiled and compiled.include_unowned:
        return Json(dict(growth.EMPTY_SERIES))

    # Match /api/collection's status default
    has_status = compiled and compiled.has_status_filter
    if not has_status:
        if where_sql == "1=1":
            where_sql = growth.UNFILTERED_WHERE
        else:
            where_sql = f"{growth.UNFILTERED_WHERE} AND ({where_sql})"

    conn = get_conn()
    try:
        # Conditional joins (mirrors /api/collection's default template —
        # the collection-anchored one, since growth is always about owned
        # rows). `price:` is resolved to the displayed price the same way,
        # so the chart and the table describe the same cards: a join that
        # pinned neither source nor the copy's finish selected on whichever
        # price any source happened to publish (de-fb1).
        extra_joins = []
        if compiled and compiled.needs_price_join:
            _, display_price_sql, display_price_joins = _display_price(conn)
            where_sql = where_sql.replace(PRICE_EXPR, display_price_sql)
            extra_joins.extend(display_price_joins)
        if compiled and compiled.needs_wishlist_join:
            extra_joins.append(
                "LEFT JOIN wishlist _wl ON _wl.oracle_id = card.oracle_id AND _wl.fulfilled_at IS NULL"
            )
        extra_joins_sql = "\n            ".join(extra_joins)

        if q:
            result = growth.compute_series(
                conn,
                where_sql=where_sql,
                params=sql_params,
                extra_joins_sql=extra_joins_sql,
                range_days=range_days,
            )
        else:
            if not growth.history_is_current(conn):
                growth.rebuild_history(conn)
            result = growth.read_history(conn, range_days)
    finally:
        conn.close()

    return Json(result)


def collection_update(get_conn, entry_id: int, data: dict):
    """Update a collection entry (partial update)."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db
    conn = get_conn()
    try:
        init_db(conn)
        repo = CollectionRepository(conn)
        entry = repo.get(entry_id)
        if entry is None:
            return Json({"error": "Not found"}, 404)
        if "printing_id" in data:
            entry.printing_id = data["printing_id"]
        if "condition" in data:
            entry.condition = data["condition"]
        if "finish" in data:
            entry.finish = data["finish"]
        if "purchase_price" in data:
            entry.purchase_price = data["purchase_price"]
        repo.update(entry)
        conn.commit()
    finally:
        conn.close()
    return Json({"ok": True})


def collection_history(get_conn, collection_id: int):
    """Return combined status + movement history for a collection entry."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db
    conn = get_conn()
    init_db(conn)
    repo = CollectionRepository(conn)

    # Status history
    status_rows = conn.execute(
        "SELECT * FROM status_log WHERE collection_id = ? ORDER BY changed_at, id",
        (collection_id,),
    ).fetchall()
    status_history = [
        {"type": "status", "id": r["id"], "collection_id": r["collection_id"],
         "from_status": r["from_status"], "to_status": r["to_status"],
         "changed_at": r["changed_at"], "note": r["note"]}
        for r in status_rows
    ]

    # Movement history
    movement_history = [
        dict(row, type="movement")
        for row in repo.get_movement_history(collection_id)
    ]

    # Combined chronological
    combined = sorted(
        status_history + movement_history,
        key=lambda x: (x["changed_at"], x["id"]),
    )

    conn.close()
    return Json({
        "status_history": status_history,
        "movement_history": movement_history,
        "combined": combined,
    })


def collection_copies(get_conn, params: dict):
    """Return per-copy data for a card (by printing_id + optional filters)."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db

    printing_id = params.get("printing_id", [""])[0]
    if not printing_id:
        return Json({"error": "printing_id required"}, 400)

    finish = params.get("finish", [""])[0] or None
    condition = params.get("condition", [""])[0] or None
    status = params.get("status", [""])[0] or None

    conn = get_conn()
    init_db(conn)

    repo = CollectionRepository(conn)
    copies = repo.get_copies(printing_id, finish=finish, condition=condition, status=status)
    conn.close()
    return Json(copies)


def collection_receive(get_conn, collection_id: int):
    """Receive a single ordered card (flip ordered -> owned)."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db
    conn = get_conn()
    try:
        init_db(conn)
        repo = CollectionRepository(conn)
        ok = repo.receive_card(collection_id)
        conn.commit()
    finally:
        conn.close()
    return Json({"received": 1 if ok else 0})


def collection_add(get_conn, data: dict):
    """Add a card to the collection manually.

    An optional `batch` descriptor — `{batch_uuid, batch_type, name,
    set_code}` — files the new copy under a batch, creating that batch on
    the first add that carries the uuid and joining it on every later one.
    The binder grid's session batch works this way: browsing posts nothing
    and so creates nothing, and one pip click is still one request.

    `condition` is optional and defaults to Near Mint.  An unrecognised one
    is a 400 rather than a coercion to the default: the binder grid's
    condition select sticks for a whole browsing pass, so silently filing a
    binder of Lightly Played cards as Near Mint would mislabel the lot.
    """
    from mtg_collector.db.models import (
        Batch,
        BatchRepository,
        CollectionEntry,
        CollectionRepository,
        WishlistRepository,
    )
    from mtg_collector.db.schema import init_db
    from mtg_collector.utils import CONDITIONS

    printing_id = data.get("printing_id", "").strip()
    if not printing_id:
        return Json({"error": "printing_id is required"}, 400)

    finish = data.get("finish", "nonfoil")
    condition = data.get("condition") or "Near Mint"
    if condition not in CONDITIONS:
        return Json({"error": f"Unknown condition: {condition}"}, 400)
    acquired_at = data.get("acquired_at")
    purchase_price = data.get("purchase_price")
    source = data.get("source", "manual")

    # Both halves of the descriptor are required when it is present: the
    # uuid is the batch's identity, and a missing type would file the copy
    # under the schema's 'corner' default and mislabel it forever.
    batch_spec = data.get("batch")
    if batch_spec is not None:
        batch_uuid = (batch_spec.get("batch_uuid") or "").strip()
        batch_type = (batch_spec.get("batch_type") or "").strip()
        if not batch_uuid:
            return Json({"error": "batch.batch_uuid is required"}, 400)
        if not batch_type:
            return Json({"error": "batch.batch_type is required"}, 400)

    if purchase_price is not None:
        purchase_price = float(purchase_price)

    conn = get_conn()
    try:
        init_db(conn)

        batch_id = None
        batch_repo = BatchRepository(conn)
        if batch_spec is not None:
            batch_id = batch_repo.get_or_create(Batch(
                id=None,
                batch_uuid=batch_uuid,
                name=batch_spec.get("name"),
                batch_type=batch_type,
                set_code=batch_spec.get("set_code"),
            ))

        collection_repo = CollectionRepository(conn)
        entry = CollectionEntry(
            id=None,
            printing_id=printing_id,
            finish=finish,
            condition=condition,
            acquired_at=acquired_at,
            purchase_price=purchase_price,
            source=source,
            batch_id=batch_id,
        )
        new_id = collection_repo.add(entry)
        if batch_id is not None:
            batch_repo.increment_card_count(batch_id, 1)

        # Auto-fulfill matching wishlist entry
        fulfilled_wishlist_id = None
        wishlist_repo = WishlistRepository(conn)
        # Check for a printing-specific wishlist entry first
        row = conn.execute(
            "SELECT id FROM wishlist WHERE printing_id = ? AND fulfilled_at IS NULL LIMIT 1",
            (printing_id,),
        ).fetchone()
        if row:
            wishlist_repo.fulfill(row["id"])
            fulfilled_wishlist_id = row["id"]
        else:
            # Check for an oracle-level wishlist entry
            row = conn.execute(
                """SELECT w.id FROM wishlist w
                   JOIN printings p ON p.oracle_id = w.oracle_id
                   WHERE p.printing_id = ? AND w.printing_id IS NULL
                     AND w.fulfilled_at IS NULL LIMIT 1""",
                (printing_id,),
            ).fetchone()
            if row:
                wishlist_repo.fulfill(row["id"])
                fulfilled_wishlist_id = row["id"]

        conn.commit()
    finally:
        conn.close()

    result = {"id": new_id}
    if fulfilled_wishlist_id is not None:
        result["fulfilled_wishlist_id"] = fulfilled_wishlist_id
    if batch_id is not None:
        result["batch_id"] = batch_id
    return Json(result)


def collection_dispose(get_conn, entry_id: int, data: dict):
    """Transition a collection entry to a disposition status."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db

    new_status = data.get("new_status")
    if not new_status:
        return Json({"error": "new_status required"}, 400)

    conn = get_conn()
    try:
        init_db(conn)

        repo = CollectionRepository(conn)
        try:
            repo.dispose(
                entry_id,
                new_status,
                sale_price=data.get("sale_price"),
                note=data.get("note"),
            )
            conn.commit()
        except ValueError as e:
            return Json({"error": str(e)}, 400)
    finally:
        conn.close()
    return Json({"ok": True})


def collection_delete(get_conn, entry_id: int):
    """Hard-delete a collection entry with lineage cleanup."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db

    conn = get_conn()
    try:
        init_db(conn)
        repo = CollectionRepository(conn)
        try:
            deleted = repo.delete_with_lineage(entry_id)
            conn.commit()
        except ValueError as e:
            return Json({"error": str(e)}, 400)
    finally:
        conn.close()
    if deleted:
        return Json({"ok": True})
    else:
        return Json({"error": "Not found"}, 404)


def collection_bulk_delete(get_conn, data: dict):
    """Bulk-delete collection entries with lineage cleanup."""
    from mtg_collector.db.models import CollectionRepository
    from mtg_collector.db.schema import init_db

    ids = data.get("ids", [])
    if not ids:
        return Json({"error": "ids array required"}, 400)

    conn = get_conn()
    try:
        init_db(conn)
        repo = CollectionRepository(conn)
        result = repo.bulk_delete(ids)
        conn.commit()
    finally:
        conn.close()
    return Json({
        "deleted": len(result["deleted"]),
        "skipped": len(result["skipped"]),
        "deleted_ids": result["deleted"],
        "skipped_ids": result["skipped"],
    })

# ===== Native routes =====

def _params(request: Request) -> dict:
    return parse_qs(request.scope["query_string"].decode("latin-1"))


def _respond(request: Request, result: Json) -> Response:
    """CrackPackHandler._send_json for an ASGI request: same policy, same headers."""
    body = json.dumps(result.obj).encode()
    content_type = "application/json"
    encoding = None
    if negotiate_gzip(request.headers.get("accept-encoding"), content_type, len(body)):
        encoding = "gzip"
    etag = compute_etag(body, encoding=encoding) if result.status == 200 else None
    headers = {"Cache-Control": CACHE_API, "Vary": "Accept-Encoding"}
    if etag:
        headers["ETag"] = etag
        if etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
    if encoding:
        body = gzip.compress(body)
        headers["Content-Encoding"] = encoding
    return Response(body, status_code=result.status, media_type=content_type,
                    headers=headers)


async def _body(request: Request):
    """The JSON body, or a Json 400 when it is not JSON."""
    try:
        return json.loads(await request.body())
    except json.JSONDecodeError:
        return Json({"error": "Invalid JSON"}, 400)


def create_router(db_path: str) -> APIRouter:
    router = APIRouter()

    def get_conn():
        from mtg_collector.cli import crack_pack_server as cps

        return tenant_connection(db_path, cps._shared_db_path)

    # sync handlers run in the threadpool, with the request's context copied,
    # so the tenant binding and the blocking sqlite calls both hold.
    @router.get("/api/collection/{cid:int}/history")
    def history(request: Request, cid: int):
        return _respond(request, collection_history(get_conn, cid))

    @router.get("/api/collection/copies")
    def copies(request: Request):
        return _respond(request, collection_copies(get_conn, _params(request)))

    @router.get("/api/collection/growth")
    def growth(request: Request):
        return _respond(request, collection_growth(get_conn, _params(request)))

    @router.get("/api/collection")
    def listing(request: Request):
        return _respond(request, collection_list(get_conn, _params(request)))

    # Legacy alias for /api/collection (24fc389): the same function, so both
    # routes take the same params and cannot drift.
    @router.get("/api/search")
    def search_alias(request: Request):
        return _respond(request, collection_list(get_conn, _params(request)))

    @router.post("/api/collection/{cid:int}/receive")
    def receive(request: Request, cid: int):
        return _respond(request, collection_receive(get_conn, cid))

    @router.post("/api/collection")
    async def add(request: Request):
        data = await _body(request)
        if isinstance(data, Json):
            return _respond(request, data)
        return _respond(request, await run_in_threadpool(collection_add, get_conn, data))

    @router.post("/api/collection/bulk-delete")
    async def bulk_delete(request: Request):
        data = await _body(request)
        if isinstance(data, Json):
            return _respond(request, data)
        return _respond(request, await run_in_threadpool(collection_bulk_delete, get_conn, data))

    @router.post("/api/collection/{entry_id:int}/dispose")
    async def dispose(request: Request, entry_id: int):
        data = await _body(request)
        if isinstance(data, Json):
            return _respond(request, data)
        return _respond(request, await run_in_threadpool(collection_dispose, get_conn, entry_id, data))

    @router.put("/api/collection/{entry_id:int}")
    async def update(request: Request, entry_id: int):
        data = await _body(request)
        if isinstance(data, Json):
            return _respond(request, data)
        return _respond(request, await run_in_threadpool(collection_update, get_conn, entry_id, data))

    @router.delete("/api/collection/{entry_id:int}")
    def delete(request: Request, entry_id: int):
        if _params(request).get("confirm", [""])[0] != "true":
            return _respond(request, Json({"error": "Must pass ?confirm=true"}, 400))
        return _respond(request, collection_delete(get_conn, entry_id))

    return router
