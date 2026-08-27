## When to escalate to Ryan, and when to just do the work

**As of 2026-08-26 there is no approval gate.** A bead you file is not deferred by default —
work proceeds unless it matches the escalate list below. If you file a bead and move on
without acting on it (or dispatching it), that is the exact bug this policy replaces: 130
real findings sat parked and invisible under the old gate, including a bug Ryan hit himself.

**Escalate** (label the bead `needs-ryan`, state the decision as a question with a default,
say what's blocked vs. not, say what it costs to reverse): anything needing a credential,
account or console only Ryan holds; destructive or irreversible action on production data;
a product decision about what a feature IS or what a number MEANS; work outside the approved
design's Intent; anything that changes when he gets paged; a choice between two defensible
options where the wrong one is expensive to undo.

**Proceed, do not ask:** bug fixes with one clearly correct answer; missing tests or a stale
spec; wrong docs; behaviour-preserving refactors and cleanups behind a green suite;
operational fixes with an existing runbook; anything an approved design already implies,
even if not itemised. **Filing is not a substitute for doing.**

## Project Overview

MTG Card Collection Builder. Web app (primary) plus a CLI (bulk ingest / scripting / batch jobs). All runtime data lives in a local SQLite database under `~/.mtgc/`. Card data, prices, and sealed-product catalogue are pulled from Scryfall, MTGJSON, and TCGPlayer **only during setup / scheduled refresh** — every page render, search, and API call hits SQLite. The web UI is what users actually touch; the CLI is for headless flows (corner / OCR / order ingestion, exports, deploy automation).

## Development notes

- **Always use `uv`** for Python operations: `uv sync`, `uv run pytest`, `uv run ruff check mtg_collector/`, `uv run mtg ...`. Never `pip`, `python -m venv`, or `make`.
- `ruff` is a dev dependency — `uv run ruff` is always available.
- **STORE DATA IN THE LOCAL DB. DO NOT add runtime calls to Scryfall / MTGJSON / any external service in request handlers.** External services are only touched during `mtg setup`, `mtg cache`, `mtg data fetch*`, and the systemd `mtgc-prices` / `mtgc-sealed-catalog` / `mtgc-edhrec` timers.
- **NEVER add fallback logic.** Errors should propagate. No fallback content, no silent defaults, no swallowed exceptions. Let it crash visibly.
- As few error paths as possible. Aggressively limit modality — defaults are good enough for everyone.
- **Tests that demonstrate bugs must fail.** A passing test means the bug is fixed; a failing test means the bug still exists. Never assert the broken behaviour.
- **After implementing any feature with UI changes, run `/qa-finish`.** This skill (`.claude/skills/qa-finish/SKILL.md`) deploys a test container, walks the feature, and writes intent + hint + implementation YAML/Python under `tests/ui/`. Do not hand-write UI scenario tests outside this workflow.

## Commands

```bash
uv sync                                                # Install deps
uv run ruff check mtg_collector/                       # Lint
uv run shot-scraper install                            # One-time: Chromium for Playwright

# --- Test tiers, in order of speed ---

# 1. Unit tests — no container, no network (~2.5 min, includes generative fuzz)
uv run pytest tests/ --ignore=tests/ui --ignore=tests/integration

# 2. Targeted search tests — fast iteration (~20s)
uv run pytest tests/test_search_compiler.py tests/test_search_corpus.py -q

# 3. Integration tests — requires running container instance (~10s)
bash deploy/setup.sh <instance> --test
systemctl --user start mtgc-<instance>
uv run pytest tests/integration/ --instance <instance>

# 4. Scryfall comparison corpus — opt-in, cached in tests/.scryfall_cache.sqlite (~30s warm)
uv run pytest tests/test_search_scryfall.py --scryfall

# 5. UI scenario tests — Playwright + Claude Vision, expensive (~15-20 min full suite)
uv run pytest tests/ui/ -v --instance <instance>

# Always-skipped: 7 order parser tests need real vendor HTML files (not in repo).

# --- App ---
mtg setup                                              # DB + Scryfall cache + MTGJSON
mtg setup --demo                                       # + ~50 demo cards
mtg setup --demo --from-fixture tests/fixtures/test-data.sqlite   # Fast bring-up
mtg crack-pack-server                                  # Web UI on port 8080

# --- Deployment (rootless Podman, per-instance isolation) ---
bash deploy/seed.sh                                    # One-time reusable seed volume (~15-30 min)
bash deploy/seed.sh --force                            # Recreate after schema migrations
bash deploy/setup.sh <name> --test                     # Pre-built fixture (~seconds)
bash deploy/setup.sh <name> --init                     # Clone seed volume (~seconds)
bash deploy/setup.sh <name>                            # No data (auto-port, inherits API key)
bash deploy/deploy.sh <name>                           # Rebuild image + restart
bash deploy/teardown.sh <name> [--purge]               # Stop / remove
bash deploy/prune-instances.sh                         # Clean up orphaned test instances
systemctl --user start mtgc-<name>                     # Start / status
```

## Web routes

The HTTP server is `mtg_collector/cli/crack_pack_server.py` — a single-file threaded stdlib `http.server` with manual path dispatch in `do_GET`/`do_POST`/`do_PUT`/`do_DELETE`. SSE is used for long-running ingest processing. No framework.

**HTML pages are dispatched from a table, not the `elif` chain.**
`mtg_collector/cli/page_routes.py` holds `PAGE_ROUTES`, and `do_GET` routes every page
through `match_page_route`, so the table *is* the routing rather than a description of it.
API endpoints stay in the chain — nobody navigates to one, and their dispatch carries
per-route parsing the table has no shape for.

Adding a page means adding a `PageRoute`, and that is deliberately the only way:
`tests/ui/test_nav_reachability.py` reads the same tuple and demands a **visible** anchor
on the rendered homepage for every non-parametrized route, at a standard *and* a narrow
viewport. Default-deny — a new page with no nav link fails the suite. Deliberate
exceptions live in that file's `NAV_EXEMPT`, each with the reason it is a decision (deep
links, legacy aliases, contextual help). Do not add a second list of routes anywhere; the
check exists because a hand-written one went stale and let `/sets` ship unlinked. It reads
the rendered DOM, never the HTML source, and at two widths: what this UI renders is
viewport-conditional in places (de-l5l), so a link present in the markup is not yet a link
a user can reach.

### HTML pages
| Path | What it serves |
|---|---|
| `/` | Homepage with nav to every section |
| `/collection` | The main collection browser (search, filter, modal, grid/table) |
| `/card/:set/:cn` | Standalone card detail page (printings, copies, price chart, history) |
| `/decks`, `/decks/:id`, `/deck-builder/:id` | Deck list + unified detail/builder page |
| `/binders` | Binder list and detail |
| `/sealed` | Sealed product inventory and open-pack flow |
| `/orders`, `/orders/:id` | Order list + per-order detail |
| `/crack` | Virtual booster pack cracker |
| `/sheets`, `/set-value` | Booster sheet explorer and per-set price reports |
| `/upload`, `/recent`, `/process`, `/disambiguate` | OCR ingest pipeline (drop → background → status → resolve ambiguous matches) |
| `/ingest-corners` | Corner-photo ingest UI |
| `/ingestor-ids` | Manual rarity / CN / set entry |
| `/ingestor-order` | Paste / upload TCGPlayer or Card Kingdom orders |
| `/import-csv` | Moxfield / Archidekt / Deckbox CSV import |
| `/search-help` | Full Scryfall-style search syntax reference |

### Key API namespaces
- `/api/collection`, `/api/collection/copies`, `/api/collection/:id/*`, `/api/collection/bulk-delete`
- `/api/search`, `/api/search-suggest`, `/api/cards/by-name`, `/api/card/by-set-cn`, `/api/set-browse/:set_code`
- `/api/decks`, `/api/decks/:id/*`, `/api/deck-builder/*`
- `/api/binders`, `/api/binders/:id/*`
- `/api/orders`, `/api/orders/:id/*`, `/api/order/{parse,resolve,commit}`
- `/api/sealed/products`, `/api/sealed/collection`, `/api/sealed/open`, `/api/sealed/prices/*`, `/api/sealed/from-tcgplayer`
- `/api/wishlist`, `/api/wishlist/bulk`
- `/api/ingest2/*` (15+ endpoints for the OCR batch pipeline), `/api/corners/*`, `/api/ingest-ids/*`, `/api/import/*`
- `/api/views`, `/api/settings`, `/api/shorten`, `/api/sets`, `/api/cached-sets`
- `/api/fetch-prices`, `/api/prices-status` (used by the scheduled price timer)
- `/api/jumpstart/*` (Jumpstart-specific helpers)

## Data model

### Core join chain

```
cards (oracle_id PK)             — abstract card identity (name, colours, mana cost, oracle text)
  └─ printings (printing_id PK)  — specific printing (art, rarity, image_uri, finishes)
       └─ collection (id PK)     — one row per physical card you own/ordered/sold
            ├─ orders (id PK)    — purchase order (vendor, totals, shipping)
            ├─ decks (id PK)     — named deck (format, sleeve, deck box, zones)
            └─ binders (id PK)   — named binder (colour, type)

sets (set_code PK)               — set metadata, `cards_fetched_at` cache marker,
                                   `base_set_size` / `total_set_size` (see Set sizes)
collection_views (id PK)         — saved filters + column layout for the collection page
```

`card → printing → collection entry → optional order` is the fundamental chain. `collection_view` (VIEW) denormalises it. `latest_prices` (VIEW) gives the most recent price per (set_code, collector_number, source, type).

### Other tables

- `wishlist` — FK to `cards` (oracle-level) or `printings` (specific). Priority, max price, fulfilled status.
- `ingest_cache` — cached OCR + Claude results by image MD5 to avoid reprocessing.
- `ingest_images` — persistent web ingest pipeline state (`READY_FOR_OCR` → `PROCESSING` → `DONE` / `ERROR`).
- `ingest_lineage` — maps collection entries back to the source image.
- `decks`, `deck_cards`, `deck_states` — decks with format, sleeve, box, location, and Jumpstart/precon origin metadata.
- `deck_expected_cards` — expected card list (precons, Jumpstart). Keyed on `printing_id`; completeness compared via `oracle_id` join.
- `binders` — colour, type, storage location.
- `collection_views` — saved filter/search configurations.
- `status_log`, `movement_log` — append-only audit of status changes and deck/binder moves.
- `settings` — key-value config (`price_sources`, `image_display`, …).
- `batches` — unified groupings for every ingestion flow (corner, OCR, CSV, manual ID, orders, sealed_open) with optional deck assignment.
- `sealed_products`, `sealed_product_cards` — MTGJSON-derived sealed product catalogue with pre-resolved card contents.
- `sealed_collection`, `sealed_prices`, `latest_sealed_prices` (VIEW) — owned sealed inventory and price history.
- `mtgjson_uuid_map`, `mtgjson_printings`, `mtgjson_booster_sheets`, `mtgjson_booster_configs`, `tcgplayer_groups` — MTGJSON / TCGPlayer reference data.
- `edhrec_recommendations` — populated by the `mtgc-edhrec` timer.
- `prices`, `price_fetch_log` — append-only price time series and ingest log.
- `collection_value_history`, `collection_value_history_meta`, `collection_rev` — the
  materialized growth series, what it was built from, and the trigger-maintained stamp
  that says when the collection last changed. See "Growth chart" under Key patterns.

Schema version is `SCHEMA_VERSION` in `db/schema.py` — read the constant, never a
number written down elsewhere. Auto-migrations live in the same file, and
`init_db` raises `SchemaIntegrityError` if the recorded version is current but
objects `SCHEMA_SQL` defines are missing (`mtg db verify` checks this on demand). Repository classes in `db/models.py`: `CardRepository`, `SetRepository`, `PrintingRepository`, `CollectionRepository`, `OrderRepository`, `WishlistRepository`, `SealedProductRepository`, `SealedProductCardRepository`, `SealedCollectionRepository`, `DeckRepository`, `BinderRepository`, `CollectionViewRepository`, `BatchRepository`.

Default DB location: `~/.mtgc/collection.sqlite` (override: `--db` or `MTGC_DB`).

### Conventions

- Collection status lifecycle: `owned` → `ordered` → `listed` → `sold` / `traded` / `gifted` / `lost` / `removed`.
- RARITY_MAP: `C` common, `U` uncommon, `R` rare, `M` mythic, `P` promo, `L` land (= common), `T` token.
- `colors`, `finishes`, `promo_types` columns store JSON arrays as TEXT — use `json.loads()`, never SQL array ops.
- `acquired_at` is stored as a full ISO 8601 UTC string (`2024-03-15T12:34:56.789Z`); the `added:` search keyword compares on the 19-char prefix in the user's local timezone.

## Key patterns

### Collection page filtering
All filtering is one Scryfall-style query bar (`?q=...`). Standard Scryfall keywords (`c`, `id`, `t`, `o`, `m`, `mv`, `pow`, `tou`, `loy`, `r`, `s`, `cn`, `a`, `ft`, `kw`, `f`, `year`, `layout`, `produces`, `is:`, `has:`) plus collection-only extensions (`status:`, `added:`, `price:`, `deck:`, `binder:`, `order:`, `direction:`, `is:unassigned` / `is:decked` / `is:bindered` / `is:wanted` / `is:unowned`). Default when no `status:` is present: `status:owned OR status:ordered`. `is:unowned` flips the query to a LEFT JOIN against `printings` so unowned cards appear (lets users add a card from the modal). Operators `:`, `=`, `!=`, `>`, `>=`, `<`, `<=` are accepted on numeric/date keywords; the autocomplete suggests both keywords and per-keyword values, with corpus-driven suggestions (artist names, set codes, year/month buckets present in the user's collection) served by `/api/search-suggest`. `added:` resolves dates in the browser's local timezone (the page sends `Intl.DateTimeFormat().resolvedOptions().timeZone` on every `/api/collection` request).

Search compiler lives in `mtg_collector/search/`: `grammar.py` (tokeniser), `transformer.py` (parser → AST), `compiler.py` (AST → SQL), `keywords.py` (canonical name registry), `dates.py` (timezone-aware date parsing).

### Set sizes

`sets.base_set_size` and `sets.total_set_size` are stored, never derived, and populated at
ingest only. `base_set_size` is MTGJSON's `baseSetSize` (where the base set ends and
boosterfun begins); `total_set_size` is Scryfall's per-set `card_count`.

**The boundary cannot be read off the treatment columns.** The obvious heuristic — plain
integer collector number, `border_color='black'`, empty `frame_effects`, not promo — puts
`fin`'s boundary at **#6**, because `frame_effects=["legendary"]` is a perfectly ordinary
base-set frame. MTGJSON says **309**, and 309 is where borderless actually starts. Any rule
built on `frame_effects` inherits that false positive.

**A size is a boundary, not a count.** `fin` has `base_set_size = 309` but **311** printings
at or below it, because suffixed numbers (`123a`, `123b`) sit inside the base range. Base
completion counts printings at or below the boundary; using the boundary value as the
denominator reads 309/309 on a binder with two empty pockets.

**NULL is permanent and legitimate** for a set no source reports a size for (2 of the
fixture's 192). The UI hides the completion bar rather than rendering 0/0 = NaN%. Nothing
here writes NULL over a stored size, and nothing inserts a `sets` row that was not already
cached.

Both ingest paths populate the columns from data they already held — `mtg cache all` from
the `card_count` it fetches to size its own backfill, `mtg data import` from the set objects
it already walks. Neither runs on a timer, so an existing database is brought forward by
`mtg data backfill-set-sizes` (one Scryfall `/sets` call plus local `AllPrintings.json`,
batched, and idempotent: a second run writes zero rows). See `mtg_collector/db/set_sizes.py`.

### Growth chart
`/api/collection/growth` has two routes to the same numbers, and `mtg_collector/db/growth.py`
holds both. A **query** is aggregated day by day inside SQLite from `collection` + `prices`;
its cost is dominated by reading every price row every held card has ever had, which grows
with the day axis. The **unfiltered** series is instead read out of `collection_value_history`
— O(days), measured 15.4 s → 0.5 ms on a 5.1 M-price-row / 15 k-card / 365-day rig, output
bit-identical.

The materialized table serves the unfiltered case *only*: a filter changes which collection
rows are summed, and there is no materializing one table per filter. That is an explicit
branch on "was a query supplied?", not a fast path with a fallback — a filtered request
never consults the table and so never has a miss to recover from. **Do not add a rule that
tries to serve some filters from it.**

Staleness is decided against three recorded facts, never a heuristic: `collection_rev`
(bumped by triggers on `collection`, and only for `printing_id` / `finish` / `acquired_at` /
`status` — a binder move or an edited note is not in the series), the last `price_fetch_log`
id, and the last day stored. `mtg data fetch-prices` rebuilds after each import; the endpoint
rebuilds on the request that first finds the table stale, because otherwise one added card
would leave the chart on the slow route until the next 06:00 timer run.

### Binder browse (`/api/set-browse/:set_code`)

One set laid out as a binder page. `mtg_collector/db/set_browse.py` holds the query;
`crack_pack_server._api_set_browse` is a thin handler over it. **One row per printing,
never per copy** — `qty` is the total and `owned` breaks it down per finish, which is the
pip row the grid draws.

**Copies are pre-aggregated in a subquery, and that is not a style choice.** The obvious
`LEFT JOIN collection c ON c.printing_id = p.printing_id AND c.status = 'owned'` fans out
one row per copy (2.41x on `sos` against prod), and the `status` term also hands the
planner a second index to choose between. **Nothing in this app runs `ANALYZE`**, so with
no `sqlite_stat1` SQLite picks `idx_collection_status` and rescans every owned row once
per printing: measured 1,141 ms against 25 ms once statistics exist. Aggregating first
leaves `printing_id` as the only join term, so the plan does not depend on statistics that
are not there — 44 ms with none at all. Do not "simplify" it back to a direct join.

**Prices key on the printing's `finishes`, not on a copy's `c.finish`** the way
`_ENRICH_JOINS` does. The pocket this view exists to show you is the one you have *not*
filled, and it has no copy to take a finish from; a printing that exists in nonfoil is
priced in nonfoil, a foil-only or etched-only one in foil.

**Sections** are `base` | `extended` | `promo`, decided by `sets.base_set_size` and nothing
else (see "Set sizes"). With `base_set_size` NULL the set is one
contiguous run — everything non-promo is `base`, which is also every pre-2019 set's shape —
and `owned_base`/`total_base` are **null**, not 0/0, so the UI hides the bar.

**All three sections are on by default** (`DEFAULT_SECTIONS`); promos used to be excluded
(de-epk). The meters count every printing in the set, so a section withheld from the default made the
header disagree with the grid beneath it by exactly the hidden rows — `hob` reported 321
printings and drew 320, the missing tile a bundle promo no control could ask for. The pills
on `/sets/:set_code` dismiss a section **by choice**, writing `sections` to the query string
with the full set elided like every other control there.

**Completion counts are computed before `q`, `filter` and `sections`**, so the header meters
do not move when the view is filtered — including when a section is dismissed. They measure
the set, not the view. Both count printings, never copies.

`limit` defaults to 250 and caps at `COLLECTION_LIMIT_MAX`; a bad `limit`, `sort`, `order`,
`filter` or `sections` is a 400 via `PageParamError`, never a silent clamp or fallback.

### HTTP response semantics — one door, policy keyed on the response

Every body leaves through `CrackPackHandler._respond`, and the caching rules
follow from **what the response is**, not from a string the caller passed.
`mtg_collector/http_cache.py` holds the decisions as pure functions.

Three policies, and there is no fourth: `CACHE_DOCUMENT` (`public, no-cache`)
for HTML and everything under `/static/*`, `CACHE_IMMUTABLE` for the
ingest-image path (whose headers are unchanged, at `public, max-age=86400,
immutable`), `CACHE_API` (`private, no-cache`) for JSON. SSE sets its own
headers and is untouched.

**`immutable` is a promise about the URL, not about the bytes**, and no URL here
is content-addressed. The ingest-image path rests on a convention — the upload
handler refuses a name that already exists — which is why its window stays a day
and not a year; a hash in the URL is what would earn more. `/static/app.css`
rests on nothing at all: it is rewritten by every deploy, so a long max-age on
it is the same bug the pages had. Every HTML page was served
`public, max-age=86400` with no validator, and because `magic.dumpster.cards`
reaches this process through a Cloudflare tunnel, the edge held each document
for a day: six deploys landed on 2026-08-25 and the public site showed none of
them. A hard refresh does not help — it defeats the browser cache, not the edge.

**The ETag varies with the encoding** — `"<h>"` identity, `"<h>-gzip"` — plus
`Vary: Accept-Encoding`. One tag for two representations is how a cache serves
gzipped bytes to a client that asked for none, or satisfies a byte range out of
the wrong representation; two tags makes that unrepresentable. For the same
reason **a Range request forces identity**, and `Accept-Ranges` is advertised
only on identity responses.

The ETag is a hash of the body, never the mtime: "did this page change on disk"
is what it has to answer, and it stays correct across a container rebuild, which
resets every mtime without changing a byte. There is deliberately **no
`Last-Modified`** — `If-None-Match` already wins whenever a client sends both,
so a second validator would be a second date-parsing error path with no caller.

An unparseable or multi-range `Range` is *ignored* (200), which is what RFC 9110
requires; only a well-formed range outside the representation is a 416.

**Verifying this needs the CDN.** `deploy/cdn-check.sh` compares the edge's ETag
with the origin's, because every localhost check passed on the evening the
public site was a day stale. See `deploy/README.md` → "CDN deploy check".

### Card data access policy
All runtime lookups MUST use the local database. Never Scryfall API. See `architecture/CARD_DATA_ACCESS.md`. The Scryfall API is only used by `mtg setup` / `mtg cache all` to populate the DB.

### Card image display
`collection.html` is the canonical reference. Card images come from the Scryfall CDN via `printings.image_uri`. The `image_display` setting (`crop` or `normal`) controls which Scryfall image size is used.

### Card detail page
Standalone at `/card/:set/:cn` (e.g. `/card/lci/150`). Served by `card_detail.html`, with `card-detail.css` and `card-detail.js`. Linked from the collection modal via the "Full page" badge. API endpoint: `GET /api/card/by-set-cn?set=X&cn=Y`.

### Unified deck page
Both `/decks/:id` and `/deck-builder/:id` serve `deck_builder.html` with `deck-builder.js` and `deck-builder.css`. The page combines the builder's type-grouped list view with the detail page's grid view, zone tabs, edit modal, expected-list import, and completeness tracking. View toggle switches between list (type-grouped, multi-column) and grid (rarity-bordered card images). Zone tabs filter the grid view; list view shows all zones combined. The deck list page (`decks.html`) links via a single "View" link to `/decks/:id`.

### Sealed product flow
`/sealed` lists products from `sealed_products` (populated by the `mtgc-sealed-catalog` timer from MTGJSON) and the user's own sealed inventory from `sealed_collection`. Opening a product calls `/api/sealed/open`, which uses pre-resolved `sealed_product_cards` rows to insert real `collection` entries (no Scryfall lookup at runtime). Sealed prices are a separate time series (`sealed_prices` + `latest_sealed_prices` view) so booster-box prices don't collide with single-card prices.

### Shared CSS/JS foundation
`shared.css` and `shared.js` in `mtg_collector/static/`. New pages should import these; legacy pages still inline their helpers. `shared.css` uses `:root` custom properties and `.site-header` (not bare `header`) to avoid collisions. `shared.js` exports: `esc`, `parseJsonField`, `renderMana`, `formatPrice`, `getRarityColor`, `RARITY_COLORS`, `DFC_LAYOUTS`, `getCkUrl`.

### Rarity / set border gradients
Cards use CSS custom properties `--rarity-color` and `--set-color` with `linear-gradient(to bottom, …)`. Use `getRarityColor(rarity)` / `RARITY_COLORS` from `shared.js`. `crack_pack.html` additionally exposes `getSetColor`, `buildCardBadges`, `buildBadges` for pack rendering.

### Price formatting
Use `formatPrice(value)` from `shared.js` for any USD display — it returns `"$3,667.51"` (thousands separators, two decimals). Pages that don't yet import `shared.js` define an inline copy at the top of their script block. The four-decimal API-cost label in `recent.html` is the only deliberate exception.

### Order ingestion
`order_parser.py` auto-detects format (`tcg_html`, `tcg_text`, `ck_text`) → `ParsedOrder`. `order_resolver.py` maps vendor set names to DB set codes via `SET_NAME_MAP` + DB lookup, then resolves to specific printings with treatment-aware matching (borderless, extended art, showcase, etched, etc.). Idempotent — duplicate `(order_number, seller_name)` is a no-op.

### OCR ingest pipeline
Web upload at `/upload` enqueues an `ingest_images` row with status `READY_FOR_OCR`. A background thread pool (`_ingest_executor` in `crack_pack_server.py`) picks it up, runs OCR + Claude vision, and moves it through `PROCESSING` → `DONE` (or `ERROR`). `/recent` shows status; `/disambiguate` is the resolution UI for ambiguous matches. `services/agent.py` implements the agentic tool-use loop (two tools: `query_local_db`, `analyze_image`). If `ANTHROPIC_API_KEY` is unset, the server logs `pending image(s) waiting — ANTHROPIC_API_KEY not set, skipping processing` and doesn't process — but it does still serve.

### Claude API retry behaviour
Exponential backoff at 3s / 6s / 12s / 24s. Bails immediately on 400 (no retry). See `services/claude.py`.

### Card ingestion via `resolve_and_add_ids()`
Both `mtg ingest-ids` and `mtg ingest-corners` funnel through `resolve_and_add_ids()` in `cli/ingest_ids.py`: look up printing by (set_code, collector_number), create a collection entry with finish / condition / source, fail visibly if not cached (tell the user to run `mtg cache all`).

### WAL mode
SQLite connections use `PRAGMA journal_mode = WAL` (set in `db/connection.py` and `crack_pack_server.py:_get_conn`). Multi-minute price-fetch transactions no longer block readers. **Backup and restore must use `sqlite3.backup()`, not `cp`** — see `tests/ui/conftest.py:_BACKUP_CMD` / `_RESTORE_CMD`. Plain `cp` over the main file leaves WAL state behind; under sustained writes the server can serve stale frames.

## Known pitfalls

- **Prices join on `(set_code, collector_number)`, NOT `printing_id`.** The `prices` table has no FK to `printings`. Always join through set_code + collector_number.
- **`deck_id` and `binder_id` are mutually exclusive.** A collection entry cannot be in both. The repository returns HTTP 409 on conflict. Use `move_cards()` to reassign atomically.
- **JSON arrays stored as TEXT.** `colors`, `finishes`, `promo_types`, `keywords` are JSON-encoded strings. Use `json.loads()`, never SQL array operations.
- **Card not in local DB → tell user to run `mtg cache all`.** Do not fall back to Scryfall API.
- **Test fixture goes stale after schema migrations.** Regenerate with `uv run python scripts/build_test_fixture.py`, then recreate the seed volume with `bash deploy/seed.sh --force`. The full fixture (with sealed product contents) requires `~/.mtgc/AllPrintings.json` — run `mtg data fetch` first.
- **HTML pages share no JS imports (legacy).** Helpers like `getRarityColor()` and `formatPrice()` are inlined in older pages. New pages should use `shared.css` + `shared.js`. Don't introduce a new ad-hoc price formatter — use `formatPrice` (or copy its body verbatim if the page can't load `shared.js`).
- **Restoring DB snapshots with `cp` under WAL mode is broken.** See the "WAL mode" patterns section. Use `sqlite3.backup()`.
- **Never use `rowid` on a shared reference table.** Deployed instances ATTACH `shared.sqlite` and shadow every table in `SHARED_TABLES` with a temp `CREATE VIEW … AS SELECT * FROM shared.<t>`. Views have no rowid, and SQLite resolves `rowid` against one to **NULL rather than an error** — so a join keyed on it silently matches nothing instead of failing loudly. Key on a real unique column (`uuid`, `printing_id`, the PK).
- **`mtgjson_printings.printing_id` is not unique.** The PK is `uuid`; MTGJSON emits one row per face of a double-faced card, and both faces carry the same Scryfall id with a *different* Card Kingdom link. Anything joining on `printing_id` must resolve to a single row first, the way `PackGenerator.get_ck_url()` and `_ENRICH_JOINS` in `crack_pack_server.py` do, or it multiplies rows.
- **`printings.card_name` is a denormalised copy of `cards.name`.** It exists so the collection's default sort can be served by `idx_printings_card_name(card_name, printing_id)`. Sort on `p.card_name`, never `card.name`: `/api/collection` groups by `p.printing_id`, which pins `printings` as the driving table, so `idx_cards_name` is unreachable for ordering no matter what the tiebreak is (measured 2.3 s vs 8.8 ms on 109,976 rows). **The GROUP BY must lead with the same column** or the sort just moves into the grouping and nothing is gained. `PrintingRepository.upsert` fills it; `rebuild_card_names()` runs beside `rebuild_fts()` after `mtg cache` to repair upstream renames.
- **Sort a set by `printings.number_sortable`, never by casting `collector_number`.** `ORDER BY CAST(collector_number AS INTEGER), collector_number` puts `A-248` *before* card #1, because `CAST('A-248' AS INTEGER)` is 0. `number_sortable` is that number encoded so it sorts — namespace, then value, then suffix — computed at ingest by `PrintingRepository.upsert` (`mtg_collector/db/collector_number.py` holds the encoding and the reasoning). It is **not** unique within a set, so close the `ORDER BY` on `p.printing_id` in the same direction; `idx_printings_set_sortable(set_code, number_sortable, printing_id)` carries printing_id for exactly that reason and serves the whole `ORDER BY` off one scan. `rebuild_number_sortable()` is the repair, but the column cannot go stale the way `card_name` can — it reads `collector_number`, which is half of `UNIQUE(set_code, collector_number)`.
- **A sort's tiebreak must follow the sort's direction.** SQLite reads an index backwards only when every ORDER BY term inverts together, so `p.card_name DESC, p.printing_id ASC` silently falls back to a full sort (4.3 s vs 10 ms). The tiebreak is there to make the order total, which it is in either direction.

## Deployment

Rootless Podman Quadlet. Each instance gets its own repo clone, image (`mtgc:<instance>`), data volume, env file, and port. No sudo.

Key files: `Containerfile` (multi-stage build), `deploy/seed.sh` (one-time seed volume), `deploy/setup.sh`, `deploy/deploy.sh`, `deploy/teardown.sh`, `deploy/prune-instances.sh`, `deploy/store-lib.sh` (which Podman store an instance lives in), `deploy/store-teardown.sh`, `deploy/store-isolation-gate.sh` (CI gate: a `--test` bring-up must write nothing to Podman's default store), `deploy/mtgc.container` (Quadlet template with `{{INSTANCE}}` / `{{PORT}}` / `{{HTTP_PUBLISH}}` / `{{TLS_MOUNT}}` placeholders), `deploy/render-quadlet.sh` (template render, called by `setup.sh`), `deploy/backup.sh` (host-side snapshot + S3 sync), `deploy/restore.sh`, scheduled units `deploy/mtgc-prices.{service,timer}`, `deploy/mtgc-sealed-catalog.{service,timer}`, `deploy/mtgc-edhrec.{service,timer}`, `deploy/mtgc-catalog-refresh.{service,timer}`, and `deploy/mtgc-backup.{service,timer}`. All instances share a single `mtgc:latest` image; per-instance tags (`mtgc:<instance>`) are aliases. macOS equivalents: `deploy/mac-setup.sh`, `deploy/mac-deploy.sh`, `deploy/mac-teardown.sh` (use `podman run` directly, no systemd).

- `~/.config/mtgc/default.env` holds the shared `ANTHROPIC_API_KEY`; `setup.sh` copies it to new instance env files automatically.
- `~/.config/mtgc/<instance>.env` — per-instance env.
- `~/.config/containers/systemd/mtgc-<instance>.container` — generated Quadlet unit.
- Service name: `mtgc-<instance>`; container name: `systemd-mtgc-<instance>`.
- Server logs a warning and skips OCR processing if `ANTHROPIC_API_KEY` is unset — it does **not** fail to start.
- `MTGC_HTTP_PORT` (optional, per-instance env) adds a **second, plain-HTTP listener** on that container port alongside the TLS listener on 8081; unset means one listener and today's behaviour. It exists for a host-local Cloudflare Tunnel origin, and is only reachable if `setup.sh --http-port <p>` also published it — always as `PublishPort=127.0.0.1:<p>:8080`, loopback hardcoded so plaintext can never face the LAN. See `deploy/README.md` → "Cloudflare Tunnel origin".
- `setup.sh --tls-certs <dir>` (optional) mounts a host directory of externally-obtained certificates at `/certs` **read-only** (`Volume=<dir>:/certs:ro,Z`); unset means no mount at all and today's generated unit. The app only reads certs — point `MTGC_TLS_CERT` / `MTGC_TLS_KEY` at paths under `/certs` to use them. Setting only one of the pair, or an unreadable path, fails startup — never a silent downgrade to self-signed. It never obtains or renews certs; that is the operator's job, and this repo deliberately ships no renewal unit and recommends no tool or cadence. How to actually get one (`tailscale cert`, or certbot DNS-01 as a fallback) is in `deploy/README.md` → "Trusted certificates". Note that fixing the self-signed cert's SAN does **not** stop browser warnings — trust is checked before naming.
- **`--http-port` and `--tls-certs` are sticky.** `setup.sh` records them in the instance env file as `MTGC_HTTP_PUBLISH_PORT` / `MTGC_TLS_CERTS_DIR` and re-applies them when the flag is omitted, because `deploy.sh` regenerates a missing Quadlet by re-running `setup.sh <instance>` with no flags — without the record it would silently drop the plaintext publish (tunnel origin dies quietly) and the cert mount (`/certs` unreadable → crash loop). An explicit flag overrides; to drop a setting, delete its line from the env file. The explicit HTTPS host port is *not* yet recorded (de-f2d).
- **`MTGC_STORE_ROOT` (optional) puts a NON-PROD instance's images, layers and volumes in an alternate Podman store** via `--root`/`--runroot` — never a `storage.conf`, so the choice cannot leak into unrelated podman use on the box. Rootless Podman's default store is under `$HOME`, which on the deploy box is the 98G root **prod itself runs from** (34G of it was podman's store, measured 2026-08-11). Unset is a strict no-op: the generated Quadlet, the timer units and every podman call are byte-identical to before. Prod never sets it. The generated Quadlet records the store in `GlobalArgs=`, and `deploy.sh` / `teardown.sh` / `restore.sh` / `backup.sh` / `prune-instances.sh` read it back — an **unstamped** unit means the default store just as definitely, so an inherited activation is dropped, not fallen through. Which disk is host config (`~/.config/mtgc/store.env`), read by CI, `store-teardown.sh`, and `setup.sh` **for every instance except `prod`** (de-oqu) — excluded by name, because `setup.sh` is also how prod is installed and where prod's 19G volume lives is not a host config file's decision. The name check is what makes the variable enforced on the path people actually use: the documented `bash deploy/setup.sh <inst> --test` does not go through `ci.yml`, so scoping the read to CI meant every by-hand bring-up kept writing a gigabyte to prod's disk unless the caller remembered to export it. An explicit `MTGC_STORE_ROOT` still wins for every instance including `prod`, and an explicit empty one is how a single run opts back out. **NEVER `podman system reset`**: it is not scoped by `--root`/`--runroot` and took the sibling project's prod down; `deploy/store-teardown.sh` is the correct way to remove a store. CI proves the
  whole thing end to end on every PR with `deploy/store-isolation-gate.sh` (de-3a0), which
  brings up a real `--test` instance in a probe store and fails if the bytes landed under
  `$HOME` instead — or if nothing got built, which would pass a leak-only check vacuously.
  **`$HOME/.local/share/containers` is shared with every other project on the box**, so the
  gate identifies this instance's own objects by name and by the `cards.dumpster.mtgc.build`
  label the `Containerfile` sets as the first instruction of each stage, and only
  asserts on the raw `du` delta when the store's object inventory shows nobody else was
  writing (de-dk3). Do not re-express any of it as a plain before/after byte comparison.
  The label, not `image history` from the tag: a multi-stage build's builder stage is a
  full ~1 GB image that is untagged and is **not** an ancestor of the runtime image, so a
  history walk misses it (de-y5g). The same list is what the gate's cleanup removes, so a
  run that fails leaves nothing behind — that path used to `exit 1` before its own
  leftover check and cost ~1 GB of prod's disk per failing run.
  See `deploy/README.md` → "Container storage" and `deploy/store-lib.sh`.
- **`mtg data check-catalog` alarms on catalog staleness by outcome, not component
  health** (de-b5q). The catalogue sat two months behind — newest set 2026-06-26 against
  upstream's 2026-08-14 — with every timer green, because every timer asks *did my
  download succeed*. This asks whether the set list is current: the lag is upstream's
  newest released set minus the newest released set in `sets`. `mtg cache all` upserts
  every Scryfall set unfiltered, so both sides read one list under one rule and a current
  mirror scores **exactly 0** — a quiet release month moves both sides together, so there
  is no release cadence to tune around. Both sides drop future-dated sets, or a raw
  `MAX(released_at)` reads the same far-future set on each side and measures nothing. It
  deliberately does **not** require the newest set's *cards*: `mtg cache all` skips cards
  with no `oracle_id`, so a token-only release stores zero printings by design and that
  rule would pin the alarm red with nothing able to clear it. STALE exits 1 → the unit
  fails → `OnFailure=` pushes the alert, so there is no second alerting path to keep in
  sync. It reads through `get_connection()`, never `sqlite3.connect()`: `sets` is in
  `SHARED_TABLES`, so a deployed instance's own `sets` is empty and the catalogue is behind
  a temp view over the ATTACHed `shared.sqlite` — opening the instance file directly reports
  a catalogue with no sets in it, a permanent red no refresh could clear. `mtgc-catalog-refresh`
  is what clears it, so this goes red on a box where that timer was never enabled — the
  correct reading, not a false positive. See
  `mtg_collector/db/catalog_freshness.py`, `deploy/mtgc-catalog-check.{service,timer}`,
  and `deploy/README.md` → "Catalog freshness check".
- **`mtg data refresh-catalog` is the whole catalogue refresh, and it is one command
  because it used to be two** (de-wdq). `mtg cache all` (Scryfall sets + printings) and
  `mtg data fetch` (MTGJSON) were both by hand, and the second is the one that stopped
  being run — which is how the catalogue got two months behind with every timer green.
  `deploy/mtgc-catalog-refresh.{service,timer}` runs it daily at 01:00, ahead of the
  sealed catalog (Mon 04:00), EDHREC (Wed 05:00), prices (06:00), and the 09:00 freshness
  check that grades it. **The unit has exactly one `ExecStart=`** — two lines would
  rebuild the same failure mode inside systemd, where a half-refresh reads as a green
  unit. Scryfall runs first because `sets` is what `check-catalog` measures, so a run that
  half-lands lands the half the alarm can see. Neither half is conditional on what is
  already on disk: both sources rebuild daily, so a skip is indistinguishable from a run
  with nothing to do. `fetch_allprintings` no longer wraps its import in a `try/except`
  that printed a warning — that swallowed exit code is what let a current file on disk sit
  beside a stale database. See `deploy/README.md` → "Catalog refresh".
- **`deploy/diskcheck.sh` is both the disk alarm and the pre-flight floor** (de-yef). /
  is 98 G and prod serves from it; it hit 100% on 2026-08-08 and again on 2026-08-11, and
  on both nights the backup produced no object and nothing said so (de-o4e). `MTGC_STORE_ROOT`
  bounded the largest producer of those bytes, but prod's own volume, the price series and
  every other project on the box are still on that disk. Run bare it is the **alarm**:
  percent-used against `MTGC_DISK_THRESHOLD` (90), pushed through the same `alert.sh`
  channel as the backup and catalog checks, always exiting 0 on a healthy disk because it
  is a timer and not a gate. Run `--floor` it is the **gate**: exit 1 below
  `MTGC_DISK_FLOOR_GB` (10) free, called by `setup.sh` and `deploy.sh` before `podman
  build` and by `ci.yml` before the isolation gate, each against the store *it has already
  resolved* so it measures the disk that run will really write to — which for a prod
  redeploy is prod's own. The gate exists because running
  out mid-build does not fail as a disk error — at 697 MB free a cargo link reported
  `ld terminated with signal 7 [Bus error]`. **There is no bypass flag**;
  `MTGC_DISK_FLOOR_GB` is the only knob. Free space is read in 1 K blocks and **truncated**,
  never from `df -BG`, which rounds up and would let 9.2 G free clear a 10 G floor. It
  watches `$HOME` *and* `MTGC_STORE_ROOT`, deduplicated by mount point, so an unconfigured box
  checks exactly one filesystem; reading `store.env` here only picks a `df` line to look at
  and is not the store selection `setup.sh` scopes away from `prod`. It deliberately frees
  nothing — which instance to prune is a judgement a timer cannot make, and
  `deploy/prune-instances.sh` stays by hand. See `deploy/README.md` → "Low-disk check".
- CI: push to `main` → auto-deploys `prod` at `/opt/mtgc-prod/`. Workflow dispatch (`gh workflow run deploy.yml -f instance=<name>`) for everything else.
- Deploy repo (private CI config + Quadlet host paths): see git history; the repo's CI workflow lives in `.github/workflows/`.

## Container validation

**Always validate UI / API changes in an isolated container before opening a PR.** Use the deployment scripts; never run the server on the host.

### Setup (Linux)

```bash
# Fast: pre-built fixture, no network
bash deploy/setup.sh <instance> --test
systemctl --user start mtgc-<instance>
sleep 5

# Full data: clone seed volume (run deploy/seed.sh once first)
bash deploy/setup.sh <instance> --init
systemctl --user start mtgc-<instance>
```

`--test` uses `tests/fixtures/test-data.sqlite` baked into the image plus `--demo` data (~50 cards + sealed products); no seed volume needed. `--init` clones the `mtgc-seed-data` volume (DB + Scryfall cache + MTGJSON catalogue + demo data) — falls back to a slow `mtg setup --demo` if the volume doesn't exist.

```bash
podman port systemd-mtgc-<instance> 8081/tcp                            # discover assigned port
```

### Setup (macOS)

```bash
brew install podman && podman machine init && podman machine start      # one-time
bash deploy/mac-setup.sh <instance> --test                              # ~seconds
bash deploy/mac-setup.sh <instance> --init                              # full data (~15-30 min)
podman port mtgc-<instance> 8081/tcp                                    # discover port
```

### Validate

The server uses HTTPS with a self-signed cert — `curl -ks` for everything. This stays the canonical form: port 8081 is HTTPS forever, and the optional `MTGC_HTTP_PORT` plaintext listener is loopback-only and off by default (see Deployment), so it is never how you validate a change.

```bash
PORT=$(podman port systemd-mtgc-<instance> 8081/tcp | grep -oP ':\K[0-9]+' | head -1)     # Linux
PORT=$(podman port mtgc-<instance> 8081/tcp | cut -d: -f2 | head -1)                       # macOS

curl -ks -o /dev/null -w "%{http_code} %{size_download}\n" "https://localhost:${PORT}/<page>"
curl -ks "https://localhost:${PORT}/" | grep -o 'href="/<page>"'
curl -ks -X POST "https://localhost:${PORT}/api/<endpoint>" \
  -H "Content-Type: application/json" -d '{}'

journalctl --user -u mtgc-<instance> -f         # Linux logs
podman logs -f mtgc-<instance>                  # macOS logs
```

### Visual validation

```bash
uv run shot-scraper "https://localhost:${PORT}/collection" \
  --browser-arg '--ignore-certificate-errors' \
  -o screenshots/collection.png
```

### Teardown

```bash
bash deploy/teardown.sh <instance> --purge          # Linux
bash deploy/mac-teardown.sh <instance> --purge      # macOS
```

### Notes
- Instance name should match your branch (e.g. `issue44`, `my-feature`).
- Data persists on the volume across container restarts; only `--purge` removes it.
- After schema migrations, recreate the seed volume (`bash deploy/seed.sh --force`) and the test fixture (`uv run python scripts/build_test_fixture.py`).
- `deploy/prune-instances.sh` cleans up orphaned test instances accumulated from interrupted runs.

## UI scenario tests

Data-driven UX regression tests using Playwright + Claude Vision. Excluded from default `pytest` runs (expensive — each scenario fans out into multiple Claude calls). Run explicitly with a live container:

```bash
uv run pytest tests/ui/ -v --instance <instance>
```

**Creating new UI tests:** after any feature with UI changes, run the `/qa-finish` skill (`.claude/skills/qa-finish/SKILL.md`). It:
1. Analyses the diff with a subagent and proposes 2-5 intent-based scenarios.
2. Deploys a test container and walks the feature with curl + the live server to gather real selectors and texts.
3. Writes intent YAML (`tests/ui/intents/`), hint YAML (`tests/ui/hints/`), and Python implementation (`tests/ui/implementations/`).
4. Runs the new tests against the container before tearing down.

Do **not** create or modify UI scenario tests outside `/qa-finish`. Per-test DB isolation is via session-scoped `sqlite3.backup()` snapshot + per-test restore (see `tests/ui/conftest.py`).

### Timeout budgets

**Every timeout in `tests/ui/` comes from `tests/ui/budget.py`, and there are two of
them.** `INTERACTION_BUDGET_MS` (500) is the app's answer to an interaction on a page
that is already loaded — the deliberate UX budget the collection-payload work exists to
defend. `ROUND_TRIP_BUDGET_MS` (5 000) is anything that crosses to the server and back: a
page load, a text assertion backed by a fetch, and **any action that might navigate**,
because `page.click` blocks until a navigation the click started commits. A 500 ms click
timeout was a navigation budget wearing an interaction budget's clothes, and that is
literally how a *successful* click failed a test — Playwright's call log showed the click
landed and the page reached `/sets`, and the harness raised anyway (de-6q2).

**Both are scaled by `host_contention()` — runnable tasks per CPU, floored at 1.0.** A
wall-clock budget on a shared box measures the box. On the 4-CPU deployment box at load
average 61-85, a `tests/ui -k sets_` run gave 14 failures of which **14 were Playwright
timeouts and 0 were assertion failures**; re-running the same scenarios alone passed. A
suite that reds without a single assertion firing is measuring the other tenants. On a
quiet box the factor is 1.0 and every timeout is byte-identical to what it was before, so
a payload regression still reds on the machine where you actually measure. Do **not**
raise a base budget to make a scenario pass — that is the thing being measured. If a
scenario is slow because of its own *setup*, move that setup under the page-load budget (a
deep-link `start_page`), as `sheets_card_zoom_overlay` and `sheets_deep_link_url_hash` do.

`TIMEOUT_CEILING_MS` (30 000) is Playwright's own default action timeout — the line past
which contention stops being the explanation. It caps what contention may *add*; it never
shrinks a timeout a caller asked for outright. The factor is sampled **once per scenario**
and held: timeouts that drift step to step make a failure unreproducible from its own log.

`tests/test_ui_budget.py` is the guard, and it is default-deny — an AST walk fails on any
`timeout=<number>` written at a call site in `replay.py`, `harness.py` or
`test_nav_reachability.py`. The bug it exists to stop is a literal per call site: with a
500 written twenty times, raising the budget means finding all twenty, and the ones nobody
found are the ones that flake.
