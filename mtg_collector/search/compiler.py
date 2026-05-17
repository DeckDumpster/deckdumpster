"""SQL compiler: walks AST nodes and produces parameterized SQL WHERE clauses."""

import sys
import time

from .ast_nodes import (
    AndNode,
    ASTNode,
    ComparisonNode,
    ExactNameNode,
    NameSearchNode,
    NotNode,
    OrNode,
)
from .keywords import COLOR_MAP, RARITY_ALIASES, RARITY_ORDER, STATUS_VALUES

ALL_COLORS = {"W", "U", "B", "R", "G"}


class CompiledQuery:
    """Result of compiling an AST into SQL."""

    __slots__ = (
        "where_sql", "params", "needs_fts", "order_by", "order_dir",
        "needs_deck_join", "needs_price_join", "needs_wishlist_join",
        "has_status_filter", "include_unowned",
    )

    def __init__(self):
        self.where_sql: str = "1=1"
        self.params: list = []
        self.needs_fts: bool = False
        self.order_by: str | None = None
        self.order_dir: str = "asc"
        self.needs_deck_join: bool = False
        self.needs_price_join: bool = False
        self.needs_wishlist_join: bool = False
        self.has_status_filter: bool = False
        self.include_unowned: bool = False


class CompileError(Exception):
    """Raised when the AST cannot be compiled to SQL."""


def compile_query(ast: ASTNode) -> CompiledQuery:
    """Compile an AST into a CompiledQuery with WHERE clause and params."""
    result = CompiledQuery()
    # Extract display modifiers before compiling
    ast = _extract_modifiers(ast, result)
    if ast is None:
        # Only modifiers, no search criteria
        return result
    sql, params = _compile_node(ast, result)
    result.where_sql = sql
    result.params = params
    return result


def explain(conn, compiled: CompiledQuery, mode: str = "collection") -> list[str]:
    """Run EXPLAIN QUERY PLAN on a compiled query. Returns plan lines."""
    full_sql = _build_full_sql(compiled, mode)
    rows = conn.execute(f"EXPLAIN QUERY PLAN {full_sql}", compiled.params).fetchall()
    return [row[3] if len(row) > 3 else str(row) for row in rows]


def execute_search(conn, compiled: CompiledQuery, mode: str = "collection",
                   status: str = "owned") -> tuple[list, dict]:
    """Execute a compiled search query and return (rows, timing_dict).

    mode: 'collection' (owned cards) or 'all' (all printings)
    status: 'owned' (default), 'all', or specific status
    """
    timings = {}

    t0 = time.monotonic()
    full_sql = _build_full_sql(compiled, mode, status)
    timings["compile_sql_ms"] = round((time.monotonic() - t0) * 1000, 1)

    t0 = time.monotonic()
    rows = conn.execute(full_sql, compiled.params).fetchall()
    timings["query_ms"] = round((time.monotonic() - t0) * 1000, 1)
    timings["row_count"] = len(rows)

    # Log slow queries
    total_ms = timings["query_ms"]
    if total_ms > 200:
        plan = explain(conn, compiled, mode)
        print(
            f"[SLOW QUERY] {total_ms:.0f}ms, {len(rows)} rows\n"
            f"  SQL: {full_sql[:200]}...\n"
            f"  PLAN: {'; '.join(plan[:5])}",
            file=sys.stderr,
        )

    return rows, timings


# ---------------------------------------------------------------------------
# Internal compilation
# ---------------------------------------------------------------------------


def _compile_node(node: ASTNode, ctx: CompiledQuery) -> tuple[str, list]:
    """Recursively compile an AST node into (sql_fragment, params)."""
    if isinstance(node, AndNode):
        parts = [_compile_node(c, ctx) for c in node.children]
        sql = " AND ".join(f"({p[0]})" for p in parts)
        params = [v for p in parts for v in p[1]]
        return sql, params

    if isinstance(node, OrNode):
        parts = [_compile_node(c, ctx) for c in node.children]
        sql = " OR ".join(f"({p[0]})" for p in parts)
        params = [v for p in parts for v in p[1]]
        return sql, params

    if isinstance(node, NotNode):
        inner_sql, inner_params = _compile_node(node.child, ctx)
        return f"NOT ({inner_sql})", inner_params

    if isinstance(node, NameSearchNode):
        return _compile_name_search(node.term, ctx)

    if isinstance(node, ExactNameNode):
        # Match the card identity (oracle_id), not just any printing with that name.
        # This returns all printings of that specific card across sets.
        return (
            "card.oracle_id = (SELECT oracle_id FROM cards WHERE name = ? COLLATE NOCASE LIMIT 1)",
            [node.name],
        )

    if isinstance(node, ComparisonNode):
        return _compile_comparison(node, ctx)

    raise CompileError(f"Unknown AST node type: {type(node)}")


def _compile_name_search(term: str, ctx: CompiledQuery) -> tuple[str, list]:
    """Compile a bare word name search.

    Matches Scryfall's behavior: bare words match card name and flavor_name
    only. Type line requires t:, oracle text requires o:.

    The card.name half is rewritten as `p.oracle_id IN (subselect)` so the
    cards table is scanned once (37k rows) instead of via per-printing index
    lookups during a 112k-row printings scan. The flavor_name half is gated
    on IS NOT NULL because only ~0.5% of printings have flavor names, which
    lets SQLite short-circuit the LIKE for the vast majority.
    """
    return (
        "(p.oracle_id IN (SELECT oracle_id FROM cards WHERE name LIKE ? COLLATE NOCASE)"
        " OR (p.flavor_name IS NOT NULL AND p.flavor_name LIKE ? COLLATE NOCASE))",
        [f"%{term}%", f"%{term}%"],
    )


def _compile_comparison(node: ComparisonNode, ctx: CompiledQuery) -> tuple[str, list]:
    """Compile a keyword comparison into SQL."""
    kw = node.keyword
    op = node.operator
    val = node.value

    # --- Color / Color Identity ---
    if kw in ("color", "color_identity"):
        return _compile_color(kw, op, val)

    # --- Type ---
    if kw == "type":
        return _compile_text_like("card.type_line", op, val)

    # --- Oracle text ---
    if kw == "oracle":
        return _compile_text_like("card.oracle_text", op, val)

    # --- Full oracle text (same as oracle for our purposes) ---
    if kw == "fulloracle":
        return _compile_text_like("card.oracle_text", op, val)

    # --- Mana value / CMC ---
    if kw == "mana_value":
        return _compile_numeric("card.cmc", op, val)

    # --- Power ---
    if kw == "power":
        return _compile_stat("p.power", op, val)

    # --- Toughness ---
    if kw == "toughness":
        return _compile_stat("p.toughness", op, val)

    # --- Loyalty ---
    if kw == "loyalty":
        return _compile_stat("p.loyalty", op, val)

    # --- Power + Toughness ---
    if kw == "powtou":
        return _compile_numeric(
            "(CAST(p.power AS REAL) + CAST(p.toughness AS REAL))", op, val,
            extra_where="p.power IS NOT NULL AND p.toughness IS NOT NULL "
                        "AND p.power != '*' AND p.toughness != '*'"
        )

    # --- Rarity ---
    if kw == "rarity":
        return _compile_rarity(op, val)

    # --- Set ---
    if kw == "set":
        if op in (":", "="):
            return "p.set_code = ? COLLATE NOCASE", [val]
        if op == "!=":
            return "p.set_code != ? COLLATE NOCASE", [val]
        return "1=1", []  # < > on sets doesn't make sense

    # --- Set type ---
    if kw == "set_type":
        if op in (":", "="):
            return "s.set_type = ? COLLATE NOCASE", [val]
        return "1=1", []

    # --- Artist ---
    if kw == "artist":
        return _compile_text_like("p.artist", op, val)

    # --- Flavor text ---
    if kw == "flavor":
        return _compile_text_like("p.flavor_text", op, val)

    # --- Watermark ---
    if kw == "watermark":
        if op in (":", "="):
            return "p.watermark = ? COLLATE NOCASE", [val]
        return "1=1", []

    # --- Keywords (abilities) ---
    if kw == "keyword":
        return _compile_json_array_contains("card.keywords", val)

    # --- Mana cost ---
    if kw == "mana":
        return _compile_text_like("card.mana_cost", op, val)

    # --- Format legality ---
    if kw == "format":
        fmt = val.lower()
        return "json_extract(card.legalities, '$.' || ?) = 'legal'", [fmt]

    if kw == "banned":
        fmt = val.lower()
        return "json_extract(card.legalities, '$.' || ?) = 'banned'", [fmt]

    if kw == "restricted":
        fmt = val.lower()
        return "json_extract(card.legalities, '$.' || ?) = 'restricted'", [fmt]

    # --- is: flags ---
    if kw == "is_flag":
        return _compile_is_flag(val, ctx)

    # --- not: flags (negate is:) ---
    if kw == "not_flag":
        sql, params = _compile_is_flag(val, ctx)
        return f"NOT ({sql})", params

    # --- has: flags ---
    if kw == "has_flag":
        return _compile_has_flag(val)

    # --- Collector number ---
    if kw == "collector_number":
        return _compile_numeric("CAST(p.collector_number AS INTEGER)", op, val)

    # --- Year ---
    if kw == "year":
        return _compile_numeric(
            "CAST(SUBSTR(s.released_at, 1, 4) AS INTEGER)", op, val
        )

    # --- Layout ---
    if kw == "layout":
        if op in (":", "="):
            return "p.layout = ? COLLATE NOCASE", [val]
        return "1=1", []

    # --- Produces mana ---
    if kw == "produces":
        colors = _resolve_color_value(val)
        if colors == "C":
            return _compile_json_array_contains("p.produced_mana", "C")
        conditions = []
        params = []
        for c in colors:
            conditions.append("p.produced_mana LIKE ?")
            params.append(f'%"{c}"%')
        if conditions:
            return f"({' AND '.join(conditions)})", params
        return "1=1", []

    # --- Collection-specific: status ---
    if kw == "status":
        ctx.has_status_filter = True
        lower_val = val.lower()
        if lower_val not in STATUS_VALUES:
            return "1=0 /* unknown status */", []
        if op in (":", "="):
            return "c.status = ?", [lower_val]
        if op == "!=":
            return "c.status != ?", [lower_val]
        return "1=1", []

    # --- Collection-specific: added (acquired_at date) ---
    if kw == "added":
        return _compile_text_like("c.acquired_at", op, val) if op in (":", "=", "!=") \
            else _compile_date("c.acquired_at", op, val)

    # --- Collection-specific: price ---
    if kw == "price":
        ctx.needs_price_join = True
        return _compile_numeric("_lp.price", op, val,
                                extra_where="_lp.price IS NOT NULL")

    # --- Collection-specific: deck ---
    if kw == "deck":
        ctx.needs_deck_join = True
        if val == "*":
            if op == "!=":
                return "dc.deck_id IS NULL", []
            return "dc.deck_id IS NOT NULL", []
        if op in (":", "="):
            return "d.name LIKE ? COLLATE NOCASE", [f"%{val}%"] if op == ":" else [val]
        if op == "!=":
            return "(d.name IS NULL OR d.name != ? COLLATE NOCASE)", [val]
        return "1=1", []

    # --- Collection-specific: binder ---
    if kw == "binder":
        if val == "*":
            if op == "!=":
                return "c.binder_id IS NULL", []
            return "c.binder_id IS NOT NULL", []
        if op in (":", "="):
            return "b.name LIKE ? COLLATE NOCASE", [f"%{val}%"] if op == ":" else [val]
        if op == "!=":
            return "(b.name IS NULL OR b.name != ? COLLATE NOCASE)", [val]
        return "1=1", []

    # Fallback: unsupported keyword, match nothing
    return "1=0 /* unsupported keyword */", []


# ---------------------------------------------------------------------------
# Color compilation
# ---------------------------------------------------------------------------


def _resolve_color_value(val: str) -> str:
    """Resolve a color value to color letters. E.g., 'rg' -> 'RG', 'azorius' -> 'WU'."""
    lower = val.lower()
    if lower in COLOR_MAP:
        return COLOR_MAP[lower]
    # Try treating each char as a color
    result = ""
    for ch in lower:
        if ch in COLOR_MAP:
            result += COLOR_MAP[ch]
    return result if result else val.upper()


def _compile_color(kw: str, op: str, val: str) -> tuple[str, list]:
    """Compile color/color_identity comparisons.

    For `c:` (colors), `:` and `>=` mean "card has all of these colors (and
    possibly more)" — Scryfall's superset semantic.

    For `id:` (color_identity), `:` defaults to `<=` (subset) — "card's
    color identity fits within these colors", matching Scryfall's commander
    deckbuilding semantic.
    """
    col = "card.colors" if kw == "color" else "card.color_identity"
    lower_val = val.lower()

    # Color identity uses subset semantics for `:` by default.
    if kw == "color_identity" and op == ":":
        op = "<="

    # Numeric color count: c=2, c>=3, etc.
    if val.isdigit():
        return _compile_numeric(f"json_array_length({col})", op, val)

    # Multicolor check
    if lower_val in ("m", "multicolor"):
        if op in (":", "="):
            return f"json_array_length({col}) >= 2", []
        if op == "!=":
            return f"json_array_length({col}) < 2", []
        return "1=1", []

    # Colorless check
    colors = _resolve_color_value(val)
    if colors == "C":
        if op in (":", "="):
            return f"({col} IS NULL OR {col} = '[]')", []
        if op == "!=":
            return f"({col} IS NOT NULL AND {col} != '[]')", []
        return "1=1", []

    # Multi-color value
    color_set = set(colors)

    if op in (":", ">="):
        # Superset: card has ALL of these colors (and possibly more)
        conditions = []
        params = []
        for c in color_set:
            conditions.append(f"{col} LIKE ?")
            params.append(f'%"{c}"%')
        return f"({' AND '.join(conditions)})", params

    if op == "=":
        # Exact: card has exactly these colors
        conditions = []
        params = []
        for c in color_set:
            conditions.append(f"{col} LIKE ?")
            params.append(f'%"{c}"%')
        conditions.append(f"json_array_length({col}) = {len(color_set)}")
        return f"({' AND '.join(conditions)})", params

    if op == "<=":
        # Subset: card only has colors from this set (no others)
        excluded = ALL_COLORS - color_set
        if not excluded:
            # All colors allowed — every card matches
            return "1=1", []
        conditions = []
        params = []
        for c in excluded:
            conditions.append(f"{col} NOT LIKE ?")
            params.append(f'%"{c}"%')
        return f"({' AND '.join(conditions)})", params

    if op == "<":
        # Strict subset: card has fewer colors, all within this set
        excluded = ALL_COLORS - color_set
        conditions = []
        params = []
        for c in excluded:
            conditions.append(f"{col} NOT LIKE ?")
            params.append(f'%"{c}"%')
        conditions.append(f"json_array_length({col}) < {len(color_set)}")
        return f"({' AND '.join(conditions)})", params

    if op == ">":
        # Strict superset: has all these colors AND more
        conditions = []
        params = []
        for c in color_set:
            conditions.append(f"{col} LIKE ?")
            params.append(f'%"{c}"%')
        conditions.append(f"json_array_length({col}) > {len(color_set)}")
        return f"({' AND '.join(conditions)})", params

    if op == "!=":
        # Not this exact color set
        inner_conditions = []
        inner_params = []
        for c in color_set:
            inner_conditions.append(f"{col} LIKE ?")
            inner_params.append(f'%"{c}"%')
        inner_conditions.append(f"json_array_length({col}) = {len(color_set)}")
        return f"NOT ({' AND '.join(inner_conditions)})", inner_params

    return "1=1", []


# ---------------------------------------------------------------------------
# Text compilation
# ---------------------------------------------------------------------------


def _compile_text_like(column: str, op: str, val: str) -> tuple[str, list]:
    """Compile a text field comparison using LIKE."""
    if op in (":", ">=", "<=", ">", "<"):
        # Contains match
        return f"{column} LIKE ? COLLATE NOCASE", [f"%{val}%"]
    if op == "=":
        return f"{column} = ? COLLATE NOCASE", [val]
    if op == "!=":
        return f"({column} IS NULL OR {column} != ? COLLATE NOCASE)", [val]
    return "1=1", []


# ---------------------------------------------------------------------------
# Numeric compilation
# ---------------------------------------------------------------------------

_SQL_OPS = {":", "=", "!=", "<", ">", "<=", ">="}
_SAFE_OPS = {"=": "=", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">=", ":": "="}


def _compile_numeric(expr: str, op: str, val: str,
                     extra_where: str | None = None) -> tuple[str, list]:
    """Compile a numeric comparison."""
    sql_op = _SAFE_OPS.get(op, "=")
    try:
        num = float(val)
    except ValueError:
        return "1=0 /* invalid number */", []
    parts = [f"{expr} {sql_op} ?"]
    params: list = [num]
    if extra_where:
        parts.insert(0, extra_where)
    return f"({' AND '.join(parts)})", params


def _compile_date(column: str, op: str, val: str) -> tuple[str, list]:
    """Compile a date comparison (ISO 8601 string ordering)."""
    sql_op = _SAFE_OPS.get(op, "=")
    return f"(SUBSTR({column}, 1, 10) {sql_op} ?)", [val]


def _compile_stat(column: str, op: str, val: str) -> tuple[str, list]:
    """Compile power/toughness/loyalty with * handling."""
    if val == "*":
        if op in (":", "="):
            return f"{column} = '*'", []
        if op == "!=":
            return f"{column} != '*'", []
        return "1=1", []
    return _compile_numeric(
        f"CAST({column} AS REAL)", op, val,
        extra_where=f"{column} IS NOT NULL AND {column} != '*'"
    )


# ---------------------------------------------------------------------------
# Rarity compilation
# ---------------------------------------------------------------------------


def _compile_rarity(op: str, val: str) -> tuple[str, list]:
    """Compile rarity comparisons with ordinal support."""
    lower_val = val.lower()

    if op in (":", "="):
        rarity_name = RARITY_ALIASES.get(lower_val, lower_val)
        return "p.rarity = ?", [rarity_name]

    if op == "!=":
        rarity_name = RARITY_ALIASES.get(lower_val, lower_val)
        return "p.rarity != ?", [rarity_name]

    # Ordinal comparisons
    ordinal = RARITY_ORDER.get(lower_val)
    if ordinal is None:
        return "1=0 /* unknown rarity */", []

    rarity_expr = (
        "CASE p.rarity "
        "WHEN 'common' THEN 0 "
        "WHEN 'uncommon' THEN 1 "
        "WHEN 'rare' THEN 2 "
        "WHEN 'mythic' THEN 3 "
        "WHEN 'special' THEN 4 "
        "WHEN 'bonus' THEN 5 "
        "ELSE -1 END"
    )
    sql_op = _SAFE_OPS.get(op, "=")
    return f"({rarity_expr}) {sql_op} ?", [ordinal]


# ---------------------------------------------------------------------------
# JSON array helpers
# ---------------------------------------------------------------------------


def _compile_json_array_contains(column: str, val: str) -> tuple[str, list]:
    """Check if a JSON array column contains a value (case-insensitive)."""
    return f"{column} LIKE ? COLLATE NOCASE", [f'%"{val}"%']


# ---------------------------------------------------------------------------
# is: / has: flags
# ---------------------------------------------------------------------------

_IS_FLAG_MAP = {
    # Printing properties
    "foil": "p.finishes LIKE '%foil%'",
    "nonfoil": "p.finishes LIKE '%nonfoil%'",
    "etched": "p.finishes LIKE '%etched%'",
    "fullart": "p.full_art = 1",
    "full": "p.full_art = 1",
    "promo": "p.promo = 1",
    "reprint": "p.reprint = 1",
    "firstprint": "p.reprint = 0",
    "reserved": "p.reserved = 1",
    "digital": "p.digital = 1",
    # Border
    "borderless": "p.border_color = 'borderless'",
    # Frame effects
    "showcase": "p.frame_effects LIKE '%showcase%'",
    "extendedart": "p.frame_effects LIKE '%extendedart%'",
    "colorshifted": "p.frame_effects LIKE '%colorshifted%'",
    "companion": "p.frame_effects LIKE '%companion%'",
    "devoid": "p.frame_effects LIKE '%devoid%'",
    "snow": "p.frame_effects LIKE '%snow%'",
    "lesson": "p.frame_effects LIKE '%lesson%'",
    "miracle": "p.frame_effects LIKE '%miracle%'",
    # Layout flags
    "split": "p.layout = 'split'",
    "flip": "p.layout = 'flip'",
    "transform": "p.layout IN ('transform', 'double_faced_token')",
    "tdfc": "p.layout IN ('transform', 'double_faced_token')",
    "mdfc": "p.layout = 'modal_dfc'",
    "meld": "p.layout = 'meld'",
    "dfc": "p.layout IN ('transform', 'modal_dfc', 'double_faced_token', 'art_series', 'reversible_card')",
    "leveler": "p.layout = 'leveler'",
    "adventure": "p.layout = 'adventure'",
    "saga": "card.type_line LIKE '%Saga%'",
    "class": "p.layout = 'class'",
    "case": "p.layout = 'case'",
    "battle": "p.layout = 'battle'",
    "mutate": "p.layout = 'mutate'",
    "prototype": "p.layout = 'prototype'",
    # Game availability
    "paper": "p.games LIKE '%paper%'",
    "mtgo": "p.games LIKE '%mtgo%'",
    "arena": "p.games LIKE '%arena%'",
    # Card type flags
    "spell": "card.type_line NOT LIKE '%Land%'",
    "permanent": "card.type_line NOT LIKE '%Instant%' AND card.type_line NOT LIKE '%Sorcery%'",
    "historic": "(card.type_line LIKE '%Legendary%' OR card.type_line LIKE '%Artifact%' OR card.type_line LIKE '%Saga%')",
    "vanilla": "(card.type_line LIKE '%Creature%' AND (card.oracle_text IS NULL OR card.oracle_text = ''))",
    "commander": "(card.type_line LIKE '%Legendary%' AND card.type_line LIKE '%Creature%')",
    "land": "card.type_line LIKE '%Land%'",
    "creature": "card.type_line LIKE '%Creature%'",
    # Security stamp
    "acorn": "p.frame_effects LIKE '%acorn%' OR json_extract(p.raw_json, '$.security_stamp') = 'acorn'",
    # Collection-specific flags (require collection mode)
    "unassigned": None,  # handled dynamically (needs deck join)
    "decked": None,      # handled dynamically (needs deck join)
    "bindered": None,    # handled dynamically
    "wanted": None,      # handled dynamically (needs wishlist join)
}

_HAS_FLAG_MAP = {
    "watermark": "p.watermark IS NOT NULL AND p.watermark != ''",
    "flavor": "p.flavor_text IS NOT NULL AND p.flavor_text != ''",
    "power": "p.power IS NOT NULL",
    "toughness": "p.toughness IS NOT NULL",
    "loyalty": "p.loyalty IS NOT NULL",
    "pt": "p.power IS NOT NULL AND p.toughness IS NOT NULL",
    "indicator": "json_extract(p.raw_json, '$.color_indicator') IS NOT NULL",
}


def _compile_is_flag(val: str, ctx: CompiledQuery | None = None) -> tuple[str, list]:
    """Compile is:X flags."""
    lower = val.lower()

    # Collection-specific dynamic flags
    if lower == "unassigned":
        if ctx:
            ctx.needs_deck_join = True
        return "dc.deck_id IS NULL AND c.binder_id IS NULL", []
    if lower == "decked":
        if ctx:
            ctx.needs_deck_join = True
        return "dc.deck_id IS NOT NULL", []
    if lower == "bindered":
        return "c.binder_id IS NOT NULL", []
    if lower == "wanted":
        if ctx:
            ctx.needs_wishlist_join = True
        return "_wl.id IS NOT NULL", []
    if lower == "unowned":
        if ctx:
            ctx.include_unowned = True
            ctx.has_status_filter = True
        return "c.id IS NULL", []

    sql = _IS_FLAG_MAP.get(lower)
    if sql:
        return sql, []
    return "1=0 /* unknown is: flag */", []


def _compile_has_flag(val: str) -> tuple[str, list]:
    """Compile has:X flags."""
    lower = val.lower()
    sql = _HAS_FLAG_MAP.get(lower)
    if sql:
        return sql, []
    return "1=0 /* unknown has: flag */", []


# ---------------------------------------------------------------------------
# Display modifier extraction
# ---------------------------------------------------------------------------


def _extract_modifiers(ast: ASTNode, ctx: CompiledQuery) -> ASTNode | None:
    """Extract order:/direction: modifiers from the AST (mutates ctx).

    Returns the AST with modifiers removed, or None if nothing remains.
    """
    if isinstance(ast, ComparisonNode):
        if ast.keyword == "order":
            ctx.order_by = ast.value.lower()
            if ctx.order_by == "price":
                ctx.needs_price_join = True
            return None
        if ast.keyword == "direction":
            ctx.order_dir = ast.value.lower()
            return None
        return ast

    if isinstance(ast, AndNode):
        remaining = []
        for child in ast.children:
            result = _extract_modifiers(child, ctx)
            if result is not None:
                remaining.append(result)
        if not remaining:
            return None
        if len(remaining) == 1:
            return remaining[0]
        return AndNode(children=remaining)

    return ast


# ---------------------------------------------------------------------------
# Full SQL generation
# ---------------------------------------------------------------------------

_SORT_MAP = {
    "name": "card.name",
    "cmc": "card.cmc",
    "mv": "card.cmc",
    "rarity": (
        "CASE p.rarity "
        "WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1 "
        "WHEN 'rare' THEN 2 WHEN 'mythic' THEN 3 ELSE 4 END"
    ),
    "set": "p.set_code",
    "color": "card.color_identity",
    "power": "CAST(p.power AS REAL)",
    "toughness": "CAST(p.toughness AS REAL)",
    "artist": "p.artist",
    "collector_number": "CAST(p.collector_number AS INTEGER)",
    "added": "c.acquired_at",
    "price": "_lp.price",
}


def _build_full_sql(compiled: CompiledQuery, mode: str = "collection",
                    status: str = "owned") -> str:
    """Build the complete SQL statement from a compiled query."""
    fts_join = ""
    if compiled.needs_fts:
        fts_join = "JOIN cards_fts ON cards_fts.rowid = card.rowid"

    order_col = _SORT_MAP.get(compiled.order_by, "card.name") if compiled.order_by else "card.name"
    direction = "DESC" if compiled.order_dir == "desc" else "ASC"
    order_clause = f"ORDER BY {order_col} {direction}"

    if mode == "collection":
        # When the query has an explicit status: filter, don't add a default
        if compiled.has_status_filter:
            status_clause = "1=1"
        elif status == "all":
            status_clause = "1=1"
        elif status == "owned":
            status_clause = "c.status IN ('owned', 'ordered')"
        else:
            status_clause = f"c.status = '{status}'"

        # Conditional JOINs for collection-specific keywords
        extra_joins = []
        if compiled.needs_deck_join:
            extra_joins.append(
                "LEFT JOIN deck_cards dc ON dc.collection_id = c.id"
                "\n            LEFT JOIN decks d ON dc.deck_id = d.id"
            )
        if compiled.needs_price_join:
            extra_joins.append(
                "LEFT JOIN latest_prices _lp ON _lp.set_code = p.set_code"
                "\n              AND _lp.collector_number = p.collector_number"
                "\n              AND _lp.price_type = 'normal'"
            )
        if compiled.needs_wishlist_join:
            extra_joins.append(
                "LEFT JOIN wishlist _wl ON _wl.oracle_id = card.oracle_id"
                "\n              AND _wl.fulfilled_at IS NULL"
            )
        extra_joins_sql = "\n            ".join(extra_joins)
        # Add binder LEFT JOIN unconditionally since binder_id is on collection
        # but we need binders table for binder:name queries
        binder_join = ""
        if "b.name" in compiled.where_sql:
            binder_join = "LEFT JOIN binders b ON c.binder_id = b.id"

        return f"""
            SELECT
                card.name, card.oracle_id, card.type_line, card.mana_cost,
                card.cmc, card.oracle_text, card.colors, card.color_identity,
                card.keywords AS card_keywords, card.legalities,
                p.printing_id, p.set_code, p.collector_number, p.rarity,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes, p.artist, p.image_uri,
                p.power, p.toughness, p.loyalty, p.layout,
                p.flavor_text, p.flavor_name, p.watermark,
                p.digital, p.reserved, p.reprint, p.games,
                s.set_name, s.set_type, s.released_at,
                c.id AS collection_id, c.finish, c.condition, c.language,
                c.purchase_price, c.acquired_at, c.source, c.status,
                c.notes, c.tags, c.tradelist, c.sale_price,
                c.binder_id, c.batch_id, c.order_id,
                COUNT(DISTINCT c.id) AS qty
            FROM collection c
            JOIN printings p ON c.printing_id = p.printing_id
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            {fts_join}
            {extra_joins_sql}
            {binder_join}
            WHERE {status_clause}
              AND ({compiled.where_sql})
            GROUP BY p.printing_id, c.finish, c.condition, c.status
            {order_clause}
        """
    else:
        # All cards mode — collection-specific keywords don't apply
        return f"""
            SELECT
                card.name, card.oracle_id, card.type_line, card.mana_cost,
                card.cmc, card.oracle_text, card.colors, card.color_identity,
                card.keywords AS card_keywords, card.legalities,
                p.printing_id, p.set_code, p.collector_number, p.rarity,
                p.frame_effects, p.border_color, p.full_art, p.promo,
                p.promo_types, p.finishes, p.artist, p.image_uri,
                p.power, p.toughness, p.loyalty, p.layout,
                p.flavor_text, p.flavor_name, p.watermark,
                p.digital, p.reserved, p.reprint, p.games,
                s.set_name, s.set_type, s.released_at,
                NULL AS collection_id, NULL AS finish, NULL AS condition,
                NULL AS language, NULL AS purchase_price, NULL AS acquired_at,
                NULL AS source, NULL AS status, NULL AS notes, NULL AS tags,
                NULL AS tradelist, NULL AS sale_price,
                NULL AS binder_id, NULL AS batch_id, NULL AS order_id,
                0 AS qty
            FROM printings p
            JOIN cards card ON p.oracle_id = card.oracle_id
            JOIN sets s ON p.set_code = s.set_code
            {fts_join}
            WHERE p.digital = 0
              AND p.layout NOT IN ('token', 'art_series', 'planar', 'emblem',
                                   'vanguard', 'scheme', 'double_faced_token')
              AND s.set_type NOT IN ('funny', 'memorabilia')
              AND ({compiled.where_sql})
            GROUP BY p.printing_id
            {order_clause}
        """
