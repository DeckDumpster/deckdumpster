# Holdings shipper and read-back (lakehouse 11)

`mtg lake` ships each tenant's holdings outbox into the tenant zone as encrypted
Parquet and reads it back. Code: `mtg_collector/lake/shipper.py`; cipher, key
layout and resolution rule are `lake/crypto.py` and `lake/resolve.py`, the same
modules the value job and the eraser use.

| verb | does |
|---|---|
| `mtg lake backfill [--tenant ID]` | append every current row to the outbox, once per tenant (`--again` to repeat); rows that predate the triggers are not in it |
| `mtg lake ship [--tenant ID] [--dest URI]` | ship past the cursor, then read back. **Exit 0** ok, **2** a tenant failed (others still ran), **3** a gap |
| `mtg lake readback` | rebuild `zone_holdings` from the zone alone |
| `mtg lake check` | the three-number check; exit 1 unless it passes |
| `mtg lake resolve-gap` | repair open gaps (run `readback` first) |

State is `$MTGC_HOME/lake/zone.sqlite` (cursor, parts shipped, gaps, parts read,
`zone_holdings`): derived and rebuildable from the zone, so losing it re-ships and
re-reads, never loses data. Environment: `MTGC_LAKE_TENANT_URI` (zone URI),
`MTGC_LAKE_MASTER_KEY_FILE`; the job runs under `role/mtgc-tenant`.

## Guarantees

- **At-least-once, cursor after PUT.** A crash between the PUT and the cursor
  re-sends the range. A part is named for its outbox range and the cipher is
  deterministic, so the retry is the same object; on another day it is a second
  object with the same events, and the resolution rule (highest seq wins) makes
  the doubled events change nothing.
- **A gap is never shipped across.** A hole in the outbox seq run means a holding
  change was lost. The shipper ships the contiguous part, records the gap in
  `ship_gap`, and exits 3 every run until it is resolved. Read-back separately
  fails (`ZoneIncomplete`) if a shipped range is missing from the zone.
- **Resolving a gap**: `readback`, then `resolve-gap` appends a `delete` for every
  zone row the table no longer holds and an `upsert` for every row it does, steps
  the cursor past the hole, and the next `ship` carries the repair.

## Prod: backfill, arm, three-number check (Ryan or the Concierge; not run by an aeon)

Preconditions, each a pass/fail: tenants migrated to schema >= 54
(`mtg tenant migrate --all`); `mtg tenant lake-key init` done and the key backed
up (`deploy/LAKE-KEYS.md`); `mtg tenant lake-key register --all`; the zone bucket
and `role/mtgc-tenant` per `deploy/LAKE-SOP.md`.

```bash
mtg tenant lake-key status                 # every active tenant: active
mtg lake backfill                          # once
mtg lake ship                              # one supervised pass; read the output
mtg lake check                             # outbox = shipped = read_back, fold equal, gaps=0
```

Only after that pass is green is the timer armed. Do not arm earlier: a timer that
exits 3 or 2 every night and is not read is a channel gone silent.

## Erasing a tenant (`mtg-erase`)

Offline-first, from the job image (never the app), with the lake master key and
`MTGC_LAKE_TENANT_URI` set under the `mtgc-tenant` role:

    mtg-erase <handle> --confirm <handle>

Order: tombstone the lake key (the shipper is refused from here on), delete every
object under `tenant/database_id=<ULID>/`, **prove** the prefix lists empty and the
key is tombstoned, clear that tenant's `zone.sqlite` rows, then detach and purge.
Exits: 0 erased and proven; 1 error before anything irreversible; 2 zone proven
empty but detach/purge unfinished (rerun); 3 objects remain, nothing detached or
purged. Every step is idempotent, so a rerun resumes. Noncurrent object versions
expire by the lifecycle rule in LAKE-SOP.md within a day.
