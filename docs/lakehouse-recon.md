# Lakehouse recon (sp-1a8j1t) — measured 2026-10-11

Evidence for the lakehouse design (bead 1). Measured from this repo's fetch code
and live upstream responses on the build box. **Not measured here:** anything that
needs the prod database (`/opt/mtgc-prod` and `~/.mtgc` do not exist on this box);
those rows say so and give the query to run on prod.

## 1. Nightly upstream fetch set and bytes

What `mtgc-catalog-refresh` (01:00), `mtgc-prices` (06:00), `mtgc-sealed-catalog` (Mon)
and `mtgc-edhrec` (Wed) actually pull — read from `cli/cache_cmd.py` and `cli/data_cmd.py`:

| Source | URL | Compressed (wire) | Raw | Cadence |
|---|---|---|---|---|
| MTGJSON AllPrintings | `mtgjson.com/api/v5/AllPrintings.json.gz` | 182.7 MB | 675.5 MB | daily |
| Scryfall `default_cards` | `api.scryfall.com/bulk-data` -> gz JSONL | 78.8 MB | ~500 MB (design's figure; not decompressed here) | daily |
| MTGJSON AllPricesToday | `.../AllPricesToday.json.gz` | 5.5 MB | 53.6 MB | daily (06:00) |
| MTGJSON Meta | `.../Meta.json` | tiny | tiny | daily |
| TCGCSV groups | `tcgcsv.com/tcgplayer/1/groups` | 0.09 MB | 0.09 MB | Mon (sealed) |
| TCGCSV per-group prices+products | `.../1/<group>/{prices,products}` x 454 groups | ~1.7 MB prices (sampled 16 groups = 61 KB, ×454/16) ; products not sampled | est. | Mon (sealed) / daily prices |
| EDHREC commander pages | `json.edhrec.com/pages/commanders/<slug>.json` | per-page, 0.2 s sleep | — | Wed |

**Booster sheets and decks are not separate fetches**: they arrive inside AllPrintings
(`mtgjson_booster_*` are derived from it), so K1's "booster sheets and decks" are
already covered by the AllPrintings object. No other upstream is touched.

Headline: **~265 MB compressed / ~1.2 GB raw per night** if everything is landed verbatim
(AllPrintings + default_cards + prices). Landing verbatim daily for a year is ≈ 97 GB
compressed. Scryfall `all_cards` (396 MB), `oracle_cards`, `rulings` etc. are *not*
fetched and should stay out of scope. Content-addressing (K1) only helps if upstream
bytes are stable between nights: AllPrintings and default_cards both carry
`updated_at`/`Last-Modified` stamps that move daily (MTGJSON 06:10 UTC, Scryfall
09:05 UTC), and they embed prices/timestamps, so **expect near-zero dedup hits on
AllPrintings and default_cards**; dedup is decided on SHA, not on the version stamp —
recommend the land step record both and dedupe on SHA only. Retaining only the newest
bulk snapshot plus a short window (not "every changed version") is what actually bounds
cost.

## 2. Price rows

- Today's `AllPricesToday` yields **112,725 UUIDs -> 380,152 rows/day** under the
  importer's rule (CK retail+buylist, TCG retail, normal+foil), one `observed_at` date.
  Before mapping to `(set_code, collector_number)`; unmapped UUIDs are dropped on
  import, so stored rows/day is somewhat lower.
- At that rate history grows ≈ **139 M rows/year** (≈ 2 GB/yr as zstd Parquet is an
  estimate, not measured).
- Existing history size in prod: **not measurable here.** On prod run:
  `SELECT COUNT(*), MIN(observed_at), MAX(observed_at) FROM prices;`
  `SELECT COUNT(*) FROM sealed_prices;` and `ls -l` the DB (CLAUDE.md cites an 11.4 GB
  prod DB and a 5.1 M-row rig; neither is the prod price count).
- Price schema: `prices(set_code, collector_number, source, price_type, price,
  observed_at)`, no FK to printings; sources `cardkingdom`/`tcgplayer`; price types
  `normal`, `foil`, `buylist_normal`, `buylist_foil`. `sealed_prices` keyed by
  `tcgplayer_product_id`.

## 3. Headroom

This box: `/` 392 G, 157 G free (59 % used). `/workspaces` does not exist here.
A verbatim year (~97 GB compressed) would not fit alongside the existing 215 G use; the
lake belongs in S3, not on local disk, and local staging needs only ~1.2 GB raw per run.

## 4. Per-tenant price-override tables (for K4)

**None exist.** There is no `manual_prices` or `conditions` equivalent. What the price
rule reads per tenant:

- `collection.printing_id`, `collection.finish` (etched is priced as foil), `status`
  (`owned`/`ordered`)
- `sealed_collection` (`sealed_product_uuid`, `quantity`, `status`)
- `settings.price_sources` (default `tcg,ck`) — picks the displayed source and so changes
  the valuation; **this per-tenant setting must ship with holdings** or valuation
  disagrees with the UI.

`collection.condition` and `purchase_price` / `sealed_collection.purchase_price` exist
but `db/enrich.py` and `_display_price()` do not read them for valuation, so they need
not ship (K4: ship only what the rule reads). Note `collection_value_history` also
depends on `acquired_at`.

## 5. EDHREC fetch set (K3)

Today (`fetch_edhrec`): legendary creatures / "can be your commander" cards **joined
through `collection` where `status='owned'`** — the fetch set is a function of
holdings, which is exactly what K3 forbids landing in the shared zone.

Replacement, from the catalog alone: drop the `JOIN collection` and the
`status` filter — same `cards` predicate (`type_line` legendary creature OR oracle text
"can be your commander") over `cards`/`printings`. This is tenant-independent; it needs
one count on a real catalog, which cannot be taken here (no catalog DB on this box).
Expect low thousands of pages rather than the owned few hundred; at 0.2 s sleep plus
latency that is ≥ tens of minutes weekly, so the land step needs a time budget, and
404s (commanders EDHREC lacks) are recorded as manifest entries, not retried.
The EDHREC pages are non-private public data; slug derivation is `_edhrec_slug`.
Also: cached-file skipping (`dest.exists()`) is by local file — in the lake it becomes
"landed this week", from the manifest.

## 6. Open items for the design

1. Prod counts for `prices`/`sealed_prices` and the EDHREC candidate-commander count
   must be taken on prod; this bead could not.
2. Dedup expectation for AllPrintings/default_cards (section 1) differs from the
   design's premise.
3. `price_sources` must be in the holdings outbox (section 4).
