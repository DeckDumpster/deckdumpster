# Card Data Access Policy

## Rule: The local database is the single source of truth

All card data at runtime MUST come from the local SQLite database. The Scryfall
API is only accessed during explicit cache-population commands:

- `mtg setup` / `mtg cache all` -- bulk download of the Scryfall dataset

**Every other code path** (ingestors, collection browsing, pack generation,
exports, etc.) reads exclusively from the local DB via repository methods:

- `PrintingRepository.get(printing_id)` -- lookup by printing ID
- `PrintingRepository.get_by_set_cn(set_code, cn)` -- lookup by set + collector number
- `CardRepository.search_by_name(name)` -- name search
- `PrintingRepository.get_by_oracle_id(oracle_id)` -- all printings of a card
- `SetRepository.normalize_code(raw)` -- normalize set codes from the DB
- `Printing.get_card_data()` -- full cached card data from `raw_json`

## Why

Using a single data source (bulk cache) guarantees consistent IDs throughout
the system and eliminates runtime network dependencies.

## How to add a new feature that needs card data

1. Assume the local DB is already populated (user ran `mtg setup` or `mtg cache all`)
2. Use repository methods to query -- never import `ScryfallBulkClient` for lookups
3. If the data isn't cached, return an error telling the user to run `mtg cache all`
4. If you need data that isn't in the current schema, add it to the bulk cache pipeline
