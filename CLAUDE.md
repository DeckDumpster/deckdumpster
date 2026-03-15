## Project Overview

MTG Card Collection Builder — Python CLI + web UI for managing Magic: The Gathering collections. Cards enter via Claude Vision (corner photos), OCR (full card photos), manual ID entry, or order ingestion (TCGPlayer/Card Kingdom). Card data lives in a local SQLite database (populated via `mtg setup` / `mtg cache all` from Scryfall bulk data). All runtime lookups use the local DB — no network calls. Web UI for collection browsing, virtual booster pack generation, image-based card ingestion, and order import. Import/export to Moxfield, Archidekt, Deckbox.

## Development notes

- **Always use `uv`** for all Python operations (not pip/venv/make): `uv sync`, `uv run pytest`, `uv run ruff check mtg_collector/`, `uv run mtg ...`
- Code, models, deploy scripts, all go in the repo.
- STORE DATA IN THE LOCAL DB. DO NOT add website queries that require the internet at runtime.
- `ruff` is a dev dependency — always available via `uv run ruff`
- **NEVER add fallback logic.** Errors should propagate to the user.
- No fallback content, no silent defaults, no swallowed exceptions.
- As few error paths as possible. Let it crash visibly.
- Tests use pre-populated `tests/fixtures/test-cards.sqlite` for offline testing. Corner identification tests require `ANTHROPIC_API_KEY`.
- Aggressively limit modality. Defaults are good enough for everyone.
- **Tests that demonstrate bugs must fail.** If a test exists to reproduce a known bug, it should assert the correct/fixed behavior — not the broken behavior. A passing test means the bug is fixed; a failing test means the bug still exists. Never write a test that passes when the bug is present.
- **After implementing any feature with UI changes, run `/qa-finish`** to generate UI scenario tests (intents, hints, implementations). This is a skill defined in `.claude/skills/qa-finish/SKILL.md`. It deploys a test container, walks the feature, and writes test artifacts under `tests/ui/`.

## Commands

```bash
uv sync                                                # Install deps
uv run pytest                                          # All tests
uv run ruff check mtg_collector/                       # Lint
uv run shot-scraper install                            # One-time: install Chromium for Playwright

# UI scenario tests (requires running container instance + ANTHROPIC_API_KEY)
uv run pytest tests/ui/ -v --instance <instance>       # Run all UI scenarios

mtg setup                                              # Init DB + cache Scryfall + fetch MTGJSON
mtg setup --demo                                       # Full setup + load demo data (~50 cards)
mtg setup --demo --from-fixture tests/fixtures/test-data.sqlite  # Fast setup from pre-built fixture
mtg setup --skip-cache --skip-data                     # Fast start if data is already loaded.
mtg crack-pack-server                                  # Start web UI on port 8080

# Deployment — rootless Podman, per-instance isolation
bash deploy/seed.sh                      # One-time: create reusable seed data volume (~15-30 min)
bash deploy/seed.sh --force              # Recreate seed volume (after schema changes)
bash deploy/setup.sh my-feature --init   # Create instance + clone seed volume (~seconds)
bash deploy/setup.sh my-feature --test   # Fast setup from pre-built fixture (~seconds, no network)
bash deploy/setup.sh my-feature          # Create instance without data (auto-port, inherits API key)
bash deploy/deploy.sh my-feature         # Rebuild image + restart
bash deploy/teardown.sh my-feature       # Stop + remove (add --purge to delete data)
systemctl --user start mtgc-my-feature   # Start instance
systemctl --user status mtgc-my-feature  # Check status
```

## Data Model

### Core join chain

```
cards (oracle_id PK)          — Abstract card identity (name, colors, mana cost)
  └─ printings (printing_id PK, FK oracle_id, FK set_code)  — Specific printing (art, rarity, image)
       └─ collection (id PK, FK printing_id, FK? order_id, FK? deck_id, FK? binder_id)
            ├─ orders (id PK)    — Purchase order (TCGPlayer/CK seller, totals, shipping)
            ├─ decks (id PK)     — Named deck (format, sleeve, deck box)
            └─ binders (id PK)   — Named binder (color, type)

sets (set_code PK)            — Set metadata, cards_fetched_at for cache status
collection_views (id PK)      — Saved filter configurations for the collection page
```

This is the fundamental chain: **card** → **printing** → **collection entry** (→ optional **order**).

- `collection_view` (VIEW) denormalizes this entire chain into one queryable view.
- `latest_prices` (VIEW) gives most recent price per card/source/type.

### Key lookups

- Card by name: `cards.name` (indexed)
- Printing by set+CN: `printings(set_code, collector_number)` (unique)
- Collection by printing ID: `collection.printing_id` (indexed)
- Prices join to printings via `(set_code, collector_number)` — **not** by printing_id

### Price data pipeline

MTGJSON UUIDs → `mtgjson_uuid_map(uuid → set_code, collector_number)` → `prices` table (append-only time series). `latest_prices` view uses global max `observed_at`. Sources: TCGplayer, CardKingdom.

### Other tables

- `wishlist` — FK to `cards` (oracle-level) or `printings` (specific). Priority, max price, fulfilled status.
- `ingest_cache` — Cached OCR + Claude results by image MD5 (avoids reprocessing).
- `ingest_images` — Persistent web UI ingest pipeline state (READY_FOR_OCR → PROCESSING → DONE/ERROR).
- `ingest_lineage` — Maps collection entries back to source images.
- `decks` — Named decks with format, sleeve color, deck box, storage location. Origin metadata: `origin_set_code`, `origin_theme`, `origin_variation` for Jumpstart/precon tracking.
- `deck_expected_cards` — Expected card list for precon/Jumpstart decks (keyed on `oracle_id`, not `printing_id`). Used for completeness tracking and reassembly.
- `binders` — Named binders with color, type, storage location.
- `collection_views` — Saved filter/search configurations for the collection page.
- `status_log` — Append-only audit of collection status changes.
- `movement_log` — Append-only audit of deck/binder assignment changes (from/to deck, binder, zone).
- `settings` — Key-value config (e.g. `price_sources`, `image_display`).
- `batches` — Unified batch groupings for all ingestion flows (corner, OCR, CSV import, manual ID, orders, sealed_open) with optional deck assignment.
- `sealed_product_cards` — Pre-resolved card contents for sealed products. Populated during MTGJSON import by resolving `contents_json` deck/card references. Used by the "Open Product" flow to add known cards to collection.
- Schema v32 with auto-migrations in `schema.py`.
- Repository classes in `models.py`: `CardRepository`, `SetRepository`, `PrintingRepository`, `CollectionRepository`, `OrderRepository`, `WishlistRepository`, `DeckRepository`, `BinderRepository`, `CollectionViewRepository`, `BatchRepository`, `SealedProductCardRepository`.
- **Deck/binder exclusivity**: A collection entry can be in one deck OR one binder, not both. `deck_id` and `binder_id` are mutually exclusive (enforced by repository logic, returns HTTP 409 on conflict). Use `move_cards()` to atomically reassign.

Default DB location: `~/.mtgc/collection.sqlite` (override: `--db` or `MTGC_DB` env).

### Conventions

- Collection status lifecycle: `owned` → `ordered` → `listed` → `sold` → `removed`
- RARITY_MAP codes: `C` common, `U` uncommon, `R` rare, `M` mythic, `P` promo, `L` land (treated as common), `T` token
- `colors`, `finishes`, `promo_types` columns store JSON arrays as TEXT — use `json.loads()`, not SQL array ops

## Key Patterns

### Card image display

`collection.html` is the canonical reference for how cards are displayed. Card images come from Scryfall CDN via `printings.image_uri`. The `image_display` setting (`crop` or `normal`) controls which Scryfall image size is used.

### Card detail page

Standalone page at `/card/:set/:cn` (e.g. `/card/lci/150`). Served by `card_detail.html`, with page-specific styles in `card-detail.css` and logic in `card-detail.js`. First consumer of the shared CSS/JS foundation. API endpoint: `GET /api/card/by-set-cn?set=X&cn=Y`. Linked from the collection modal via "Full page" badge.

### Unified deck page

Both `/decks/:id` and `/deck-builder/:id` serve `deck_builder.html` with `deck-builder.js` and `deck-builder.css`. The page combines the builder's type-grouped list view with the detail page's grid view, zone tabs, edit modal, expected list import, and completeness tracking. View toggle switches between list (type-grouped, multi-column) and grid (card images with rarity borders). Zone tabs filter the grid view; list view shows all zones combined. Card names link to `/card/:set/:cn`. Deck list page (`decks.html`) links via single "View" link to `/decks/:id`.

### Shared CSS/JS foundation

`shared.css` and `shared.js` in `mtg_collector/static/` consolidate common styles and utilities duplicated across pages. New pages should import these; existing pages are untouched. `shared.css` uses CSS custom properties (`:root` variables) and `.site-header` (not bare `header`) to avoid collisions. `shared.js` exports: `esc()`, `parseJsonField()`, `renderMana()`, `getRarityColor()`, `RARITY_COLORS`, `DFC_LAYOUTS`, `getCkUrl()`.

### Rarity/set border gradients

Cards use CSS custom properties `--rarity-color` and `--set-color` with `linear-gradient(to bottom, ...)`. Shared JS helpers in `shared.js`: `getRarityColor(rarity)`, `RARITY_COLORS`. Also available in `crack_pack.html`: `getSetColor(cardSetCode, packSetCode)`, `buildCardBadges(card, packSetCode)`, `buildBadges(card, packSetCode)`. Use these for any new card display.

### Collection page filtering

Only search queries and include-unowned toggle trigger server fetches. All other filters (color, rarity, set, type, finish, status, CMC, date, price) and sorting are applied **client-side** for instant responsiveness.

### Card data access policy

All runtime card lookups MUST use the local database, never the Scryfall API. See `architecture/CARD_DATA_ACCESS.md`. Scryfall API is only used during `mtg setup` / `mtg cache` to populate the local DB.

### Bulk data import

Scryfall bulk data is used only during `mtg setup` / `mtg cache all` to populate the local DB. `ScryfallBulkClient` in `services/bulk_import.py` handles this with 100ms rate limiting. 3 HTTP requests total for ~80k cards.

### Web server architecture

`crack_pack_server.py` is a single-file threaded HTTP server (stdlib `http.server`). Routes are dispatched in `do_GET`/`do_POST`/`do_PUT`/`do_DELETE` via URL path matching. SSE for long-running operations (ingest processing). No framework — raw request handling.

### Order ingestion

`order_parser.py` auto-detects format (tcg_html, tcg_text, ck_text) → `ParsedOrder`. `order_resolver.py` maps vendor set names to DB set codes via `SET_NAME_MAP` + DB lookup, then resolves to specific printings with treatment-aware matching. Idempotent — duplicate order_number + seller_name skipped.

### Agentic OCR (`services/agent.py`)

Claude tool-use loop with two tools: `query_local_db` (SQL against local SQLite) and `analyze_image` (Claude Vision). Used by the web UI ingest pipeline for card identification from photos.

### Claude API retry behavior

Exponential backoff at 3s, 6s, 12s, 24s intervals. Bails immediately on 400 errors (no retry). See `services/claude.py`.

### Card ingestion via `resolve_and_add_ids()`

Both `ingest-ids` and `ingest-corners` funnel through `resolve_and_add_ids()` in `cli/ingest_ids.py`:
1. Look up printing in local DB by set + collector number
2. Create collection entry with finish, condition, source metadata
3. If card not found, fail with error telling user to run `mtg cache all`

## Known Pitfalls

- **Prices join on `(set_code, collector_number)`, NOT `printing_id`.** The `prices` table has no FK to `printings`. Always join through set_code + collector_number.
- **`deck_id` and `binder_id` are mutually exclusive.** A collection entry cannot be in both. The repository returns HTTP 409 on conflict. Use `move_cards()` to reassign atomically.
- **JSON arrays stored as TEXT.** `colors`, `finishes`, `promo_types` are JSON-encoded strings. Use `json.loads()`, never SQL array operations.
- **Card not in local DB → tell user to run `mtg cache all`.** Do not fall back to Scryfall API. The card simply isn't cached yet.
- **Test fixture goes stale after schema migrations.** Regenerate with `uv run python scripts/build_test_fixture.py`, then recreate seed volume with `bash deploy/seed.sh --force`. Full fixture (with sealed product contents) requires `~/.mtgc/AllPrintings.json` — run `mtg data fetch` first.
- **HTML pages share no JS imports (legacy).** Helpers like `getRarityColor()` are copy-pasted between existing pages. New pages should use `shared.css` + `shared.js` instead. The card detail page (`card_detail.html`) is the first to do so.

## Deployment

Rootless Podman Quadlet. Each instance: separate repo clone, own image (`mtgc:<instance>`), data volume, env file, port. No sudo.

Key files: `Containerfile` (multi-stage build), `deploy/seed.sh` (one-time seed volume), `deploy/setup.sh`, `deploy/deploy.sh`, `deploy/teardown.sh`, `deploy/mtgc.container` (Quadlet template with `{{INSTANCE}}`/`{{PORT}}` placeholders). All instances share a single `mtgc:latest` image; per-instance tags (`mtgc:<instance>`) are aliases. macOS equivalents: `deploy/mac-setup.sh`, `deploy/mac-deploy.sh`, `deploy/mac-teardown.sh` (use `podman run` directly, no systemd).

- `~/.config/mtgc/default.env` has the shared API key; setup.sh copies it to new instances automatically
- `~/.config/mtgc/<instance>.env` — per-instance env file
- `~/.config/containers/systemd/mtgc-<instance>.container` — generated Quadlet unit
- Service name: `mtgc-<instance>`, container name: `systemd-mtgc-<instance>`
- Server checks `ANTHROPIC_API_KEY` at startup and fails fast if missing
- CI: push to main → auto-deploys `prod` at `/opt/mtgc-prod/`. Workflow dispatch for other instances.
- Deploy repo (private CI config): `rgantt/efj-mtgc-deploy`

## Container Validation

**Always validate new features in isolated containers before creating PRs.** This uses the standard deployment scripts with demo data pre-loaded. Do not run the application locally or use `mtg` commands directly on the host.

### Setup (Linux)

From the repo clone with your feature branch checked out:

```bash
# Fast path: pre-built fixture, no network needed (~seconds)
bash deploy/setup.sh <instance> --test
systemctl --user start mtgc-<instance>
sleep 5

# Full path: clone seed volume (requires seed.sh first)
bash deploy/seed.sh
bash deploy/setup.sh <instance> --init
systemctl --user start mtgc-<instance>
sleep 5                                     # Wait for server startup
```

`--test` uses a pre-built fixture DB baked into the container image — no seed volume or network required. `--init` clones the seed volume (run `seed.sh` first). Both load demo data (~50 cards + sealed products).

Discover the assigned port:

```bash
podman port systemd-mtgc-<instance> 8081/tcp
```

### Setup (macOS)

Prerequisites (one-time):

```bash
brew install podman
podman machine init
podman machine start    # Also needed after each reboot
```

Then create an instance:

```bash
bash deploy/mac-setup.sh <instance> --test   # Fast: pre-built fixture (~seconds)
bash deploy/mac-setup.sh <instance> --init   # Full: download + init data (~15-30 min)
```

The script auto-starts the container and prints the URL. Discover the port:

```bash
podman port mtgc-<instance> 8081/tcp
```

### Validate

The server uses HTTPS with a self-signed cert. Use `curl -ks` for all requests.

```bash
# Linux:
PORT=$(podman port systemd-mtgc-<instance> 8081/tcp | grep -oP ':\K[0-9]+' | head -1)
# macOS:
PORT=$(podman port mtgc-<instance> 8081/tcp | cut -d: -f2 | head -1)

# 1. Verify new page loads (HTTP 200 + non-empty body)
curl -ks -o /dev/null -w "%{http_code} %{size_download}" "https://localhost:${PORT}/<your-page>"

# 2. Verify nav link exists on homepage
curl -ks "https://localhost:${PORT}/" | grep -o 'href="/<your-page>"'

# 3. Test API endpoints with edge-case inputs (empty body, missing fields)
curl -ks -X POST "https://localhost:${PORT}/api/<your-endpoint>" \
  -H "Content-Type: application/json" -d '{}'
```

Check logs if anything fails:

```bash
# Linux:
journalctl --user -u mtgc-<instance> -f
# macOS:
podman logs -f mtgc-<instance>
```

### Visual Validation

Use `shot-scraper` to screenshot key pages for visual regression checks. The self-signed cert requires `--browser-arg '--ignore-certificate-errors'`.

```bash
mkdir -p screenshots

uv run shot-scraper "https://localhost:${PORT}/" \
  --browser-arg '--ignore-certificate-errors' \
  -o screenshots/index.png

uv run shot-scraper "https://localhost:${PORT}/collection" \
  --browser-arg '--ignore-certificate-errors' \
  -o screenshots/collection.png

uv run shot-scraper "https://localhost:${PORT}/sealed" \
  --browser-arg '--ignore-certificate-errors' \
  -o screenshots/sealed.png
```

### Teardown

```bash
# Linux:
bash deploy/teardown.sh <instance> --purge       # Stop + remove container, volume, env, and image
# macOS:
bash deploy/mac-teardown.sh <instance> --purge   # Stop + remove container, volume, env, and image
```

### Notes

- Instance name should match your branch/feature (e.g., `issue44`, `my-feature`)
- **For UI tests, prefer `--test`** — uses a pre-built fixture DB (~27 MB, 11 sets) baked into the image. No seed volume or network needed. Starts in seconds.
- **For full data, use `--init`** — clones the seed volume. Run `bash deploy/seed.sh` first (fast no-op if it exists).
- `--test` uses `tests/fixtures/test-data.sqlite` (regenerate with `uv run python scripts/build_test_fixture.py`).
- `--init` clones the `mtgc-seed-data` volume (DB, Scryfall cache, MTGJSON data, ~50 demo cards). If no seed volume exists, it falls back to the slow `mtg setup --demo` path.
- After schema migrations, recreate the seed volume with `bash deploy/seed.sh --force` and regenerate the test fixture.
- Data persists on the volume across container restarts. Only `--purge` removes it.

## UI Scenario Tests

Data-driven UX regression tests using Claude Vision + Playwright. Excluded from `uv run pytest` by default (expensive — each scenario makes Claude API calls). Run them explicitly:

```bash
uv run pytest tests/ui/ -v --instance <instance>
```

**Creating new UI tests:** After implementing any feature with UI changes, run the `/qa-finish` skill (defined in `.claude/skills/qa-finish/SKILL.md`). This skill:
1. Uses a subagent to analyze the diff and propose 2-5 intent-based scenarios
2. Deploys a test container and walks the feature with `curl`
3. Writes intent YAML (`tests/ui/intents/`), hint YAML (`tests/ui/hints/`), and implementation Python (`tests/ui/implementations/`)

Do NOT create or modify UI scenario tests outside of the `/qa-finish` workflow.

