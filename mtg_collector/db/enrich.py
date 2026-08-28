"""Display price and Card Kingdom link, expressed as joins on the query that needs them.

Every list of cards this app renders carries the same three derived values: a
Card Kingdom price, a TCGplayer price, and a Card Kingdom product link.  They
used to be gathered by a second pass over the result -- a `WHERE (set_code,
collector_number) IN (...)` and a `WHERE printing_id IN (...)`, each building a
statement whose bound-parameter count was sized by the result set.  On
/api/collection that reached 225,618 parameters against a
SQLITE_MAX_VARIABLE_NUMBER of 250,000 (de-ckq).  Every join below binds zero
parameters and matches at most one row, so neither the SQL text nor the row
cardinality depends on how large the result is.

Two things make each join single-row rather than a fan-out:

  * `latest_prices` has PRIMARY KEY (set_code, collector_number, source,
    price_type), so pinning source and price_type pins the row.
  * `printing_id` is *not* unique in `mtgjson_printings` -- MTGJSON emits one
    row per face of a double-faced card, and both faces carry the same Scryfall
    id with a different Card Kingdom link.  Resolving to a uuid first keeps the
    join single-row, and resolving it the way `PackGenerator.get_ck_url()` does
    -- same index seek, same first row -- is what makes the collection list, the
    deck page and the card detail page link the same card to the same product.

**Which finish to price in is the caller's fact, not this module's**, which is
why every entry point takes a SQL predicate for it.  A list of copies you hold
prices each copy in the finish it was recorded in (`COPY_IS_FOIL`); a list of
printings prices the printing (`PRINTING_IS_FOIL`), because the pocket a binder
view exists to show you is the one you have *not* filled and an unowned
printing has no copy to take a finish from.  Passing the wrong one is not a
formatting difference: it shows a foil card at the nonfoil price.

The query must alias `printings` as `p`, and `collection` as `c` if it uses
`COPY_IS_FOIL`.
"""

from typing import List

#: A copy in hand: `collection.finish` records what was actually acquired.
#: Etched prices as foil.  A NULL finish -- a row reached through a LEFT JOIN
#: that found no copy -- prices as nonfoil.
COPY_IS_FOIL = "c.finish IN ('foil', 'etched')"

#: A printing with no copy behind it.  A printing that exists in nonfoil is
#: priced in nonfoil; one that does not (foil-only and etched-only printings,
#: 718 of the 7,645-printing fixture) is priced in foil.
#:
#: `finishes` is a JSON array in a TEXT column, so this is a substring test; no
#: other finish value contains "nonfoil".  The COALESCE is what keeps a NULL
#: `finishes` on the foil side rather than making the whole predicate NULL and
#: silently flipping it.
PRINTING_IS_FOIL = "COALESCE(p.finishes, '') NOT LIKE '%nonfoil%'"

#: Card Kingdom publishes a buylist and a retail price; the buylist wins when
#: present.
CK_PRICE_SQL = "COALESCE(_ck_buy.price, _ck_retail.price)"
TCG_PRICE_SQL = "_tcg.price"


def enrich_price_joins(is_foil: str) -> List[str]:
    """The price joins alone -- everything a display price can be built from.

    Totals scan the whole result and never render a link, so they take this
    rather than the full set.
    """
    return [
        "LEFT JOIN latest_prices _ck_buy ON _ck_buy.set_code = p.set_code"
        " AND _ck_buy.collector_number = p.collector_number"
        " AND _ck_buy.source = 'cardkingdom'"
        f" AND _ck_buy.price_type = CASE WHEN {is_foil} THEN 'buylist_foil' ELSE 'buylist_normal' END",
        "LEFT JOIN latest_prices _ck_retail ON _ck_retail.set_code = p.set_code"
        " AND _ck_retail.collector_number = p.collector_number"
        " AND _ck_retail.source = 'cardkingdom'"
        f" AND _ck_retail.price_type = CASE WHEN {is_foil} THEN 'foil' ELSE 'normal' END",
        "LEFT JOIN latest_prices _tcg ON _tcg.set_code = p.set_code"
        " AND _tcg.collector_number = p.collector_number"
        " AND _tcg.source = 'tcgplayer'"
        f" AND _tcg.price_type = CASE WHEN {is_foil} THEN 'foil' ELSE 'normal' END",
    ]


#: Resolve the double-faced ambiguity to one uuid before joining.  See the
#: module docstring.
CK_URL_JOIN = (
    "LEFT JOIN mtgjson_printings _mp ON _mp.uuid ="
    " (SELECT uuid FROM mtgjson_printings WHERE printing_id = p.printing_id LIMIT 1)"
)


def enrich_joins(is_foil: str) -> List[str]:
    """Prices and the Card Kingdom link, for a query that renders both."""
    return enrich_price_joins(is_foil) + [CK_URL_JOIN]


def enrich_columns(is_foil: str) -> str:
    """`ck_price`, `tcg_price` and `ck_url`, as a SELECT-list fragment.

    A foil copy falls back to the nonfoil URL when there is no foil one; a
    missing row leaves the empty string rather than NULL, because the client
    renders the link unconditionally.
    """
    return ",\n".join([
        f"{CK_PRICE_SQL} AS ck_price",
        f"{TCG_PRICE_SQL} AS tcg_price",
        f"COALESCE(NULLIF(CASE WHEN {is_foil} THEN _mp.ck_url_foil END, ''),"
        " _mp.ck_url, '') AS ck_url",
    ])
