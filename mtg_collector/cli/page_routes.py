"""The HTML pages this server serves, as data instead of an if/elif chain.

`do_GET` dispatches every page through :func:`match_page_route`, so this tuple
is not a description of the routing — it *is* the routing. That matters because
the nav-reachability suite (`tests/ui/test_nav_reachability.py`) reads the same
tuple to assert every page can be reached from the homepage: a route added here
is a route the test demands a nav link for, and there is no second list to keep
in step. Adding a page any other way (an `elif` in `do_GET`) both bypasses this
table and escapes that check, which is exactly the gap that let a nav group go
stale unnoticed.

API endpoints stay in `do_GET`'s chain. They are not pages, nobody navigates to
one, and their dispatch carries per-route parsing this table has no shape for.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageRoute:
    """One user-facing HTML page.

    `parametrized` routes match by prefix, the way `/card/:set/:cn` and
    `/decks/:id` do: the server hands the same file to every path under the
    prefix and the page reads its own id out of `location.pathname`.
    """

    path: str
    template: str
    parametrized: bool = False
    #: Handler method name whose return value is spliced into the page as
    #: /*INIT_DATA*/ (see `_serve_static_with_data`). Only `/decks` uses it.
    init_data: str | None = None


PAGE_ROUTES: tuple[PageRoute, ...] = (
    PageRoute("/", "index.html"),
    PageRoute("/crack", "crack_pack.html"),
    PageRoute("/sheets", "explore_sheets.html"),
    PageRoute("/collection", "collection.html"),
    PageRoute("/sealed", "sealed.html"),
    PageRoute("/deck-builder", "deck_builder.html"),
    PageRoute("/deck-builder/", "deck_builder.html", parametrized=True),
    PageRoute("/decks", "decks.html", init_data="_decks_init_data"),
    PageRoute("/decks/", "deck_builder.html", parametrized=True),
    PageRoute("/binders", "binders.html"),
    PageRoute("/search-help", "search-help.html"),
    PageRoute("/set-value", "set_value.html"),
    PageRoute("/sets", "sets.html"),
    # /sets/:set_code → the binder grid. The set code is read from the
    # path by the page itself, the way /card/:set/:cn does it.
    PageRoute("/sets/", "set_browse.html", parametrized=True),
    # /card/:set/:cn → card detail page
    PageRoute("/card/", "card_detail.html", parametrized=True),
    PageRoute("/upload", "upload.html"),
    PageRoute("/recent", "recent.html"),
    PageRoute("/process", "recent.html"),
    PageRoute("/disambiguate", "disambiguate.html"),
    PageRoute("/ingest-corners", "ingest_corners.html"),
    PageRoute("/batches", "batches.html"),
    PageRoute("/corner-batches", "batches.html"),
    # /batches/:id → batch detail page (JS reads pathname)
    PageRoute("/batches/", "batch_detail.html", parametrized=True),
    PageRoute("/ingestor-ids", "ingest_ids.html"),
    PageRoute("/ingestor-order", "ingest_order.html"),
    PageRoute("/import-csv", "import_csv.html"),
    PageRoute("/orders", "orders.html"),
    # /orders/:id → order detail page (JS reads pathname)
    PageRoute("/orders/", "order_detail.html", parametrized=True),
)

_EXACT = {r.path: r for r in PAGE_ROUTES if not r.parametrized}
# Longest prefix first, so /decks/ cannot shadow a longer prefix added under it.
_PREFIXES = tuple(
    sorted((r for r in PAGE_ROUTES if r.parametrized), key=lambda r: -len(r.path))
)


def match_page_route(path: str) -> PageRoute | None:
    """The page route serving `path`, or None if `path` is not a page.

    Exact routes win over prefixes, which is what keeps `/deck-builder` (the
    empty builder) distinct from `/deck-builder/:id` even though both end up
    at the same file.
    """
    exact = _EXACT.get(path)
    if exact is not None:
        return exact
    for route in _PREFIXES:
        if path.startswith(route.path):
            return route
    return None
