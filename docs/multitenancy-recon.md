# Multi-tenancy recon: prod's real layout (sp-thsnbu)

Status: **code-derived half done; host-measured half NOT done.** The aeon that wrote this
runs in a worktree with no prod access (`/opt/mtgc-prod`, `~/.mtgc`, and prod's podman
volumes do not exist for it; `podman ps` is empty). Every row marked MEASURE below needs
Ryan or the Concierge on the prod host. Nothing here is a measurement of prod.

## What the code says (verified in this tree)

| Question | Answer from code | Confidence |
|---|---|---|
| Split or monolithic? | Decided per deployment by `MTGC_SHARED_DB`. `setup.sh` adds it (`/shared/shared.sqlite`, volume `mtgc-shared-ref:/shared:ro`) **only if** volume `mtgc-shared-ref` exists when the Quadlet is generated, and never for `--test`. So prod is split iff that volume exists and its unit was (re)generated after. | Mechanism certain; prod's state MEASURE |
| Does /shared mount? | `get_shared_db_path()` returns None when the env var is set but the file is missing, so a failed mount **silently degrades to monolithic reads** (empty temp-view-less catalog tables in main). Bead 10 must make this fatal in multi mode. | Certain; prod MEASURE |
| What is in the shared catalogue? | `SHARED_TABLES`: cards, sets, printings, **prices**, price_fetch_log, mtgjson_*, sealed_products, sealed_product_cards, **sealed_prices**, tcgplayer_groups, edhrec_recommendations; views latest_prices, latest_sealed_prices. Prices are shared, so the price series (the bulk of the 11.5 GB) belongs in `shared.sqlite`, not per-tenant. | Certain |
| Per-tenant content | Everything else: collection, orders, decks/deck_cards/deck_states, binders, wishlist, ingest_*, batches, settings, collection_views, status/movement logs, collection_value_history*, collection_rev. | Certain |
| FK enforcement | `foreign_keys=ON` only when NOT split (connection.py), so split mode has no FK enforcement across the catalogue. Tenant files will have FKs to catalogue tables they cannot enforce. | Certain |
| Backup | `deploy/backup.sh` snapshots only `${volume}/collection.sqlite` via `sqlite3.backup()` plus image trees, tars, `aws s3 sync` (no --delete). It does **not** include `shared.sqlite` on the `/shared` volume. In split mode that is the user data; restorability of the tarball is unproven. | Certain on content; restore MEASURE |
| Edge caching | `_respond`: JSON is `private, no-cache` (`CACHE_API`), HTML `public, no-cache`, hashed assets immutable. So **no /api response is edge-cacheable by policy**. Per-tenant API leakage via Cloudflare is not possible from headers alone; a Cloudflare cache rule/Page Rule could still override. | Policy certain; live edge MEASURE |

## MEASURE: run on the prod host (read-only), paste results below

```
V=$(podman volume inspect mtgc-prod-data --format '{{.Mountpoint}}')
podman volume exists mtgc-shared-ref && echo shared-vol-present
grep -E 'MTGC_SHARED_DB|Volume=' ~/.config/containers/systemd/mtgc-prod.container
podman exec systemd-mtgc-prod ls -la /data /shared
podman exec systemd-mtgc-prod printenv MTGC_SHARED_DB
# table row counts + size per table (needs sqlite3_analyzer or dbstat)
for f in $V/collection.sqlite /path/to/shared.sqlite; do
  sqlite3 -readonly "$f" "select name, sum(pgsize)/1048576 as mb from dbstat group by name order by mb desc limit 15;"
  sqlite3 -readonly "$f" "select count(*) from collection; select count(*) from printings; select count(*) from prices;"
done
# restorable backup: newest tarball (local or s3), into scratch
d=$(mktemp -d); aws s3 cp s3://$MTGC_BACKUP_S3_BUCKET/mtgc-prod/daily/<newest>.tar.gz $d/
tar -xzf $d/*.tar.gz -C $d && sqlite3 -readonly $d/*/collection.sqlite 'pragma integrity_check; select count(*) from collection;'
# edge: compare headers via the tunnel
curl -sI https://magic.dumpster.cards/api/collection | grep -iE 'cache-control|cf-cache-status|age'
```

Decision this feeds (bead 10): if prod is split, tenant #1 = copy of the user-owned tables of
`collection.sqlite` (small), `shared.sqlite` stays; if monolithic, the migration must first
`db split` (prices/catalogue out), which is a downtime step per `law-a-cutover-takes-downtime`.

## Results

_Pending host measurements._
