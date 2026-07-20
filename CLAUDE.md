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

sets (set_code PK)               — set metadata, `cards_fetched_at` cache marker
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

## Deployment

Rootless Podman Quadlet. Each instance gets its own repo clone, image (`mtgc:<instance>`), data volume, env file, and port. No sudo.

Key files: `Containerfile` (multi-stage build), `deploy/seed.sh` (one-time seed volume), `deploy/setup.sh`, `deploy/deploy.sh`, `deploy/teardown.sh`, `deploy/prune-instances.sh`, `deploy/mtgc.container` (Quadlet template with `{{INSTANCE}}` / `{{PORT}}` placeholders), `deploy/backup.sh` (host-side snapshot + S3 sync), `deploy/restore.sh`, scheduled units `deploy/mtgc-prices.{service,timer}`, `deploy/mtgc-sealed-catalog.{service,timer}`, `deploy/mtgc-edhrec.{service,timer}`, `deploy/mtgc-backup.{service,timer}`. All instances share a single `mtgc:latest` image; per-instance tags (`mtgc:<instance>`) are aliases. macOS equivalents: `deploy/mac-setup.sh`, `deploy/mac-deploy.sh`, `deploy/mac-teardown.sh` (use `podman run` directly, no systemd).

- `~/.config/mtgc/default.env` holds the shared `ANTHROPIC_API_KEY`; `setup.sh` copies it to new instance env files automatically.
- `~/.config/mtgc/<instance>.env` — per-instance env.
- `~/.config/containers/systemd/mtgc-<instance>.container` — generated Quadlet unit.
- Service name: `mtgc-<instance>`; container name: `systemd-mtgc-<instance>`.
- Server logs a warning and skips OCR processing if `ANTHROPIC_API_KEY` is unset — it does **not** fail to start.
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

The server uses HTTPS with a self-signed cert — `curl -ks` for everything.

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
