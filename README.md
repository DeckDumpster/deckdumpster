# MTG Collection Builder

A web app (with CLI fallback) for managing a Magic: The Gathering collection. Cards land in a local SQLite database via photo, OCR, manual entry, or order import; the web UI is where you actually live with them — browse, search, organise into decks and binders, track sealed product, and watch prices over time.

All runtime lookups hit the local DB. No internet calls during normal use. Scryfall, MTGJSON, and TCGPlayer/CardKingdom data are pulled once into the DB during setup and refreshed in the background.

## What's in the web UI

Start the server and open `http://localhost:8080`. The site is the primary interface; the CLI exists for bulk ingest and scripting.

### Collection (`/collection`)
- Scryfall-style search bar — colours, types, oracle text, mana value, rarity, set, artist, keywords, format legality, plus collection-only filters (`status:`, `added:`, `price:`, `deck:`, `binder:`, `is:foil`, `is:unowned`, `is:wanted`, `order:price`, …). Autocomplete suggests both keywords and values; `added:today` resolves in the browser's local timezone. Full syntax at `/search-help`.
- Switch between table and image-grid views; saved views remember your filter and column layout.
- Click any card → modal with copies, prices, lineage, deck/binder assignment, dispose-to-sold/traded/gifted/lost workflow, and a "Full page" link to `/card/:set/:cn`.
- `is:unowned` flips the query against the full printings catalogue so you can add cards you don't yet own from the same surface.

### Card detail (`/card/:set/:cn`)
- Standalone page for one printing — front/back faces (flips for DFC), all printings of the same oracle card, copies you own, price history chart with purchase-price reference lines, full status/movement audit trail.

### Decks (`/decks`, `/deck-builder/:id`)
- Create decks with format, sleeve colour, deck box, and storage location.
- Builder shows mainboard / sideboard / commander zones; switch between a type-grouped list and a rarity-bordered grid.
- Import an expected card list (precon / Jumpstart contents) to track deck completeness.
- Move a card between decks or out to a binder atomically — a card lives in exactly one container.

### Binders (`/binders`)
- Named binders with colour and type. Cards move freely between binders and decks; assignment is mutually exclusive.

### Sealed (`/sealed`)
- Booster boxes, bundles, packs, precons, prerelease kits — anything MTGJSON tracks as a sealed product.
- Add to inventory with cost; mark opened and route the contained cards into the main collection; bulk-dispose unopened stock; chart sealed-product price history.

### Orders (`/orders`, `/orders/:id`)
- Imported orders from TCGPlayer or Card Kingdom, with per-card pricing and totals. Receive an order in one click to flip everything from `ordered` → `owned`.

### Ingestion surfaces
- `/upload` — drag photos in; the server runs OCR + Claude vision in a background pipeline (`/recent` shows progress, `/disambiguate` resolves ambiguous matches).
- `/ingest-corners` — corner-only photos for fast bulk ID without identifying the card name.
- `/ingestor-ids` — type rarity / collector number / set when you have the cards in hand.
- `/ingestor-order` — paste a TCGPlayer or Card Kingdom order (HTML or text) and the server resolves treatments to specific printings.
- `/import-csv` — Moxfield, Archidekt, or Deckbox CSV.

### Other
- `/crack` — virtual booster cracker with live prices for whatever the sheets produce.
- `/sheets`, `/set-value` — explore booster sheet layouts and per-set price totals.
- `/search-help` — full search syntax reference.

## Search syntax (quick reference)

Standard Scryfall keywords: `c`/`color`, `id`/`identity`, `t`/`type`, `o`/`oracle`, `m`/`mana`, `mv`/`cmc`, `pow`, `tou`, `loy`, `r`/`rarity`, `s`/`set`, `b`/`block`, `cn`/`number`, `a`/`artist`, `ft`/`flavor`, `kw`/`keyword`, `f`/`format`, `banned`, `restricted`, `year`, `layout`, `produces`, `is:`, `has:`, `unique:`.

Collection-only keywords: `status:` (`owned` / `ordered` / `listed` / `sold` / `traded` / `gifted` / `lost` / `removed`), `added:`, `price:`, `deck:`, `binder:`, `order:` (sort field), `direction:`. Date and numeric keywords accept the full operator set (`:`, `=`, `!=`, `>`, `>=`, `<`, `<=`). `added` accepts ISO calendar prefixes (`2024`, `2024-03`, `2024-03-15`), full ISO datetimes, and relative shortcuts (`today`, `yesterday`, `7d`, `30d`, `1y`).

## Getting started

```bash
git clone https://github.com/DeckDumpster/deckdumpster.git
cd deckdumpster
uv sync

# One-shot setup: DB + Scryfall bulk cache + MTGJSON data
mtg setup

# Or with ~50 cards of demo data
mtg setup --demo

# Or fast bring-up from the pre-built fixture
mtg setup --demo --from-fixture tests/fixtures/test-data.sqlite

# Start the web UI
mtg crack-pack-server          # http://localhost:8080
```

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- `ANTHROPIC_API_KEY` (only needed for photo-based ingestion — set in env or `~/.config/mtgc/default.env`)
- [Podman](https://podman.io/) (only for the deployment scripts under `deploy/` and the integration / UI test suites)

Data lives in `~/.mtgc/` by default (override with `MTGC_HOME`). The collection DB defaults to `~/.mtgc/collection.sqlite` (override with `--db` or `MTGC_DB`).

## CLI

The CLI is a thin wrapper for headless ingestion and scripting. Common entry points:

| Command | What it does |
|---|---|
| `mtg setup [--demo] [--from-fixture PATH]` | Init DB, bulk-cache Scryfall, fetch MTGJSON |
| `mtg crack-pack-server [--port N]` | Start the web UI (default port 8080) |
| `mtg ingest-ids --id R 0200 EOE [foil] [--source X]` | Add cards by rarity / collector # / set |
| `mtg ingest-corners photo.jpg ...` | Add cards from corner photos (Claude Vision) |
| `mtg ingest-ocr photo.jpg ...` | Add cards from full card photos (local OCR + Claude) |
| `mtg ingest-order order.html` | Import a TCGPlayer / Card Kingdom order |
| `mtg orders {list,show,receive}` | Manage orders |
| `mtg import file.csv` | Import from Moxfield / Archidekt / Deckbox (auto-detected) |
| `mtg export -f {moxfield,archidekt,deckbox} -o out.csv` | Export collection |
| `mtg list [--set X] [--name Y] [--foil] ...` | List collection entries |
| `mtg show ID` / `mtg edit ID ...` / `mtg delete ID` | Inspect or edit one entry |
| `mtg stats` | Collection summary |
| `mtg wishlist {add,list,fulfill,remove}` | Wishlist management |
| `mtg cache all [--force]` | Refresh the local Scryfall cache |
| `mtg data fetch` / `mtg data fetch-prices` | Pull MTGJSON catalogue + prices |
| `mtg db {init,refresh,split}` | Database maintenance |

Run `mtg <command> --help` for full flags on any subcommand.

## Data model (one-line tour)

A physical card is a row in `collection`, linked to a `printings` row (specific set + collector number), which links to a `cards` row (oracle identity). Each collection entry carries status (`owned` / `ordered` / `listed` / `sold` / `traded` / `gifted` / `lost` / `removed`), condition, finish, language, purchase price, optional sale price, source, optional FK to `orders`, and optional mutually-exclusive FK to either `decks` or `binders`. Status changes append to `status_log`; deck/binder moves append to `movement_log`. Prices live in an append-only `prices` time series with a `latest_prices` view. Sealed products have their own collection table (`sealed_collection`) and price series.

## Deployment

The repo ships rootless Podman Quadlet scripts under `deploy/` for Linux and parallel `mac-*.sh` scripts for macOS. Each instance gets its own image tag, data volume, env file, and port — no sudo, no port collisions. CI auto-deploys `prod` on push to `main`.

```bash
bash deploy/setup.sh my-feature --test    # ~seconds, pre-built fixture
systemctl --user start mtgc-my-feature
bash deploy/teardown.sh my-feature --purge
```

See `CLAUDE.md` for the deployment details.

## Development

```bash
uv sync                                                              # Install deps
uv run ruff check mtg_collector/                                     # Lint
uv run pytest tests/ --ignore=tests/ui --ignore=tests/integration    # Unit tests
```

Three test tiers beyond the unit suite (each requires a running container instance): `tests/integration/` for API tests, `tests/ui/` for Playwright + Claude Vision UX scenarios, and the opt-in `--scryfall` corpus that compares the local search compiler against Scryfall's live results. `CLAUDE.md` has the full matrix.

## License

MIT
