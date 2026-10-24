# Route families and the strangler (multi-tenancy N3)

The ASGI app (`mtg_collector/asgi_app.py`) is the only listener. A family is
**native** once its routes are FastAPI handlers in `mtg_collector/routes/<family>.py`
and registered in `create_app` ahead of the legacy catch-all; anything a native
family does not claim still falls through to `CrackPackHandler` via the adapter.
Route counts are `do_GET`/`do_POST`/`do_PUT`/`do_DELETE` branches in
`crack_pack_server.py` as of 2026-10-11 (page routes are `PAGE_ROUTES`, 28 of them).

| # | Family | Routes (prefix: branches) | Status |
|---|---|---|---|
| 1 | **collection** | `/api/collection*` (GET 4, POST 4, PUT 1, DELETE 2), `/api/search` alias | **native** (sp-5y2g2x) |
| 2 | decks + deck-builder | `decks` 7/11/1/2, `deck-builder` 5/5/1/1 | legacy |
| 3 | binders + set-browse | `binders` 3/3/1/2, `set-browse` 1 | legacy |
| 4 | ingest (OCR, corners, ids, import, batches) | `ingest2` 8/13, `ingest`, `corners` 2, `ingest-ids` 2, `import` 3, `batches` 2/3/-/1, `corner-batches` | legacy |
| 5 | orders | `orders` 3/2/1, `order` 3 | legacy |
| 6 | sealed | `sealed` 8/7/1/1 | legacy |
| 7 | catalog reads | `sets`, `cached-sets`, `card`, `cards`, `printings`, `products`, `sheets`, `precons`, `jumpstart`, `generate`, `set-value-data`, `price-history`, `prices-status`, `fetch-prices`, `search-suggest` | legacy |
| 8 | wishlist, views, settings, shorten | `wishlist` 1/3/-/1, `views` 2/1/1/1, `settings` 1/-/1, `shorten` | legacy |
| 9 | pages and static | `PAGE_ROUTES`, `/static/*`, ingest images | legacy |

The last bead deletes the adapter and `CrackPackHandler`.

## How a family is ported

- The handler logic becomes plain functions `(get_conn, ...) -> Json` in the family
  module. The native route calls them; the legacy `CrackPackHandler._api_*` method
  delegates to the same function (`_send_result`), so the two cannot drift while
  the existing suites (which drive the legacy methods) still run unchanged.
- Query parameters are read with `parse_qs`, exactly as before, so status codes and
  error bodies are unchanged; they are not turned into FastAPI-validated models
  (that would change 400s to 422s, a behaviour change this series does not make).
- Path ids use Starlette's `:int` convertor. A non-numeric id does not match the
  native route and falls through to the adapter, which answers as it always did.
- JSON leaves through `_respond` in the family module, which applies the same
  `CACHE_API` / ETag / gzip policy as `CrackPackHandler._respond`.
- The connection comes from the family's `get_conn`, which calls `current_tenant()`
  first and so raises outside a resolved request.

## Expired sign-in on an in-page action (sp-3ojucg)

`OidcMiddleware` (`mtg_collector/oidc.py`) is where it is caught. A request with
`Sec-Fetch-Mode: navigate` (or, with no such header, a GET) gets the 303 to
`/auth/login?return_to=<path+query>`. Anything else (fetch/XHR) gets a 401 with
`X-Login-Required: 1`, since a fetch cannot follow a cross-origin redirect.
`static/session-guard.js`, injected first in `<head>` of every document by
`AssetHasher.rewrite`, wraps `fetch`/XHR and turns that 401 into
`/auth/login?return_to=<current page>`; login then returns there.
