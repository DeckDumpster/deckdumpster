# Lakehouse: the timer chain, disaster recovery and the restore drill

## The chain (K8)

One chain per instance, **08:00 UTC**, five links, each `After=` the previous.
pokedumpster's chain runs 06:00-07:30 on the same box; this one does not overlap it.

| link | unit | runs | role | writes |
|---|---|---|---|---|
| land | `mtgc-land` | `mtg data land`, `fetch-edhrec`; then `lake-sync.sh raw` | `mtgc-lake` | `raw/` only; **no catalogue byte** |
| derive | `mtgc-derive` | `mtg data derive`, `import-edhrec` | none (offline) | `shared.sqlite`, its sole writer |
| prices | `mtgc-prices` | `import-sealed-products`, `fetch-prices`, `fetch-sealed-prices`, `lake-build`, `lake-verify`; then `lake-sync.sh raw`, `catalog` | `mtgc-lake` | `raw/`, Iceberg `prices` / `sealed_prices` |
| ship | `mtgc-ship` | `mtg lake ship` | `mtgc-tenant` | `tenant/` |
| value | `mtgc-value` | `mtg lake value` | `mtgc-tenant` | each tenant's `collection_value_history` |

Every link is a one-off `podman run` of `localhost/mtgc:<instance>`, the image
`deploy.sh` rebuilds and tags on every redeploy, so a deploy rebuilds the job image
and the next night's chain runs it. A link that fails fails its unit and pages
(`OnFailure=`); the links behind it still start (a ship that exits 3 must not hide
a catalogue that landed), and `ship`'s exit 2 / 3 stay visible in the journal.
`derive` reads the newest run that landed **every** catalogue input
(`landing.newest_catalog_run`), not the newest run: land's EDHREC pages and the
prices link are runs of their own.

The Iceberg warehouse and its SQL catalogue are local files
(`~/.local/share/mtgc-lake/<inst>/iceberg`), mirrored to `s3://<lake>/lake/catalog/`
by `lake-sync.sh catalog`. They stay local because `value` runs as `mtgc-tenant`,
which is denied `lake/` by design.

### Retired

`mtgc-catalog-refresh` (01:00), `mtgc-sealed-catalog` (Mon) and `mtgc-edhrec` (Wed)
are gone, and the 06:00 `mtgc-prices` is now the third link. `deploy.sh` stops,
disables and deletes the three from the host on every redeploy
(`mtgc_retire_units`). `mtgc-catalog-check` (09:00) is unchanged and grades the
chain's derive.

### Arming

Installing units never arms them. Once per instance, after `deploy/LAKE-SHIP.md`'s
supervised pass is green and the master key is backed up (`LAKE-KEYS.md`):

```bash
bash deploy/chain.sh status <inst>   # 0/5 enabled, no problems listed
bash deploy/chain.sh arm <inst>
```

`arm` enables all five or none, and refuses a chain that is not whole: a unit
missing, a link not ordered after its predecessor, a link off the 08:00 UTC clock,
a retired timer still on the host, `lake.env` without `MTGC_LAKE_S3_BUCKET` /
`MTGC_LAKE_TENANT_URI`, or `tenant-master.key` missing or not mode 600.
`status` exits 1 on a half-armed chain.

## Disaster recovery

Restore in this order. Every step has a pass/fail; do not start one before the last
passes. Needed: AWS access to the three buckets, the lake master key from the
password manager, and the pinned litestream binary (`deploy/litestream-install.sh`).

1. **Registry first.** It names every tenant and holds the `lake_tenant_key`
   tombstones, so nothing below may run against an empty one.
   `litestream restore -o ~/registry.sqlite "$(...)"` as in `deploy/restore.sh`.
   Pass: `mtg tenant list` shows the tenants; `lake-key status` shows the same
   tombstones as before. An empty or tombstone-less registry is **stop**, not
   "carry on": absence is never permission (`LAKE-KEYS.md`).
2. **Master key.** Write the password-manager copy to
   `~/.config/mtgc/<inst>/tenant-master.key`, mode 600 (directory 700). Pass:
   `mtg tenant lake-key status` prints the fingerprint recorded when it was minted.
   Never restore the key from S3: it was never put there.
3. **Catalogue, cold, from a named partition.** Pick the raw run to rebuild from
   (`aws s3 ls --recursive s3://<lake>/raw/ | grep _manifest.json`; the drill picks
   the newest complete one). Pull its manifests and every `_objects/sha256=...`
   they name into `~/.local/share/mtgc-lake/<inst>/raw`, then:
   `mtg data derive --run <RUN_ID> --raw-root <that dir>` in the job image.
   Pass: it exits 0 and `mtg data check-catalog` reports lag 0 for that night. A
   `ReplayMiss` means the partition is incomplete: choose another, never the network.
4. **Prices.** Restore `s3://<lake>/lake/catalog/` into
   `~/.local/share/mtgc-lake/<inst>/iceberg`; `mtg data lake-verify` agrees with
   SQLite, or `mtg data lake-build` re-appends the days SQLite holds.
5. **Zone, reconciled by emit.** The zone is the source of truth for holdings and
   `zone.sqlite` is derived: `mtg lake readback` rebuilds `zone_holdings` from the
   bucket alone. A tenant whose database is newer than the zone is repaired by
   emit, not by hand: `mtg lake backfill --again`, `mtg lake ship`,
   `mtg lake resolve-gap` (after `readback`) as in `LAKE-SHIP.md`. Pass: `mtg lake
   check` prints `OK` for every tenant.
6. Redeploy (`deploy.sh <inst>`), `chain.sh status <inst>`, then `chain.sh arm <inst>`.

## The restore drill (against the real buckets)

```bash
bash deploy/lake-drill.sh prod --master-key /path/to/password-manager-copy [--partition RUN_ID]
```

Run by Ryan or the Concierge on the deploy box, **never by an aeon or CI**. It
restores the registry from its replica, checks the key against the box's,
cold-rebuilds the catalogue from the named raw partition in a job container and
compares `cards` / `printings` / `sets` / `mtgjson_printings` row counts with the served
catalogue, then rebuilds `zone_holdings` from the bucket and compares per-tenant row
counts with the live zone. All in a mode-700 scratch directory; live files and
buckets are only read. Exit 0 only if every claim held; a failure names its step and
keeps the scratch for inspection.

Drill cadence is Ryan's call. The first run is the acceptance of this runbook:
record its output on the bead that arms the chain.
