"""mtg-erase: prove a tenant's lake data deleted, then detach and purge it (lakehouse 13).

Runs in the job image, never in the app.  The order is offline-first, because
the tenant zone is the part of a tenant that outlives its SQLite file:

    1. tombstone the lake key   (nothing can seal or open this tenant's objects again;
                                 the shipper is refused, so nothing re-ships mid-erase)
    2. erase the zone           (delete every object under tenant/database_id=<ULID>/)
    3. prove it                 (list the prefix: empty, key state tombstoned)
    4. clear the derived state  (zone.sqlite rows, zone_holdings included)
    5. detach, then purge       (registry.detach_tenant / purge_tenant)

Each step is idempotent and the run resumes where the last one stopped, so a
crash is repaired by running it again.  Detach and purge happen only after the
proof, so a tenant is never purged with its zone data still standing.

Exit codes:
    0  erased and proven; the tenant is detached and purged
    1  error before anything irreversible (bad argument, registry, zone unreachable)
    2  partial: the zone is proven empty but detach or purge did not finish; rerun
    3  proof failed: objects remain under the prefix after the delete; nothing was
       detached or purged

Versioned buckets keep noncurrent versions of deleted keys; the lifecycle rule
in deploy/LAKE-SOP.md expires them within a day.  The proof here is of what the
zone lists, which is what mtgc-tenant can see.
"""

import argparse
import os
import sqlite3
import sys
from contextlib import closing

from mtg_collector.db import registry
from mtg_collector.lake import keys as lake_keys
from mtg_collector.lake import resolve as rs
from mtg_collector.lake import shipper

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PARTIAL = 2
EXIT_UNPROVEN = 3

_STATE_TABLES = (
    "ship_cursor", "ship_part", "ship_gap", "zone_part",
    "zone_readback", "zone_holdings", "ship_backfill",
)


def erase_zone(zone: shipper.Zone, database_id: str) -> int:
    """Delete every object under the tenant's prefix.  Returns how many."""
    keys = zone.list(rs.tenant_prefix(database_id))
    for k in keys:
        zone.delete(k)
    return len(keys)


def prove_empty(zone: shipper.Zone, database_id: str) -> list[str]:
    """What the zone still lists under the prefix.  Empty is the proof."""
    return zone.list(rs.tenant_prefix(database_id))


def clear_state(state: sqlite3.Connection, database_id: str) -> int:
    n = 0
    state.execute("BEGIN IMMEDIATE")
    try:
        for t in _STATE_TABLES:
            n += state.execute(f"DELETE FROM {t} WHERE database_id = ?", (database_id,)).rowcount
    except BaseException:
        state.execute("ROLLBACK")
        raise
    state.execute("COMMIT")
    return n


def _find(reg, handle: str):
    """The latest tenant a handle named, in any state."""
    row = reg.execute(
        "SELECT * FROM user WHERE handle = ? ORDER BY created_at DESC, database_id DESC LIMIT 1",
        (handle,),
    ).fetchone()
    if not row:
        raise registry.RegistryError(f"no tenant with handle {handle!r}")
    return row


def erase(reg, state, zone, handle: str, *, log=print) -> int:
    row = _find(reg, handle)
    database_id = row["database_id"]
    log(f"tenant {handle} ({database_id}) is {registry.state(row)}")

    lake_keys.tombstone(reg, database_id, "tenant erased")
    log("  lake key tombstoned")

    log(f"  zone: deleted {erase_zone(zone, database_id)} object(s)")
    left = prove_empty(zone, database_id)
    if left:
        log(f"  PROOF FAILED: {len(left)} object(s) remain under {rs.tenant_prefix(database_id)}")
        for k in left[:10]:
            log(f"    {k}")
        return EXIT_UNPROVEN
    if lake_keys.state(reg, database_id) != "tombstoned":
        log("  PROOF FAILED: key is not tombstoned")
        return EXIT_UNPROVEN
    log(f"  proven: {rs.tenant_prefix(database_id)} lists empty, key tombstoned")

    log(f"  derived state: cleared {clear_state(state, database_id)} row(s)")

    try:
        row = _find(reg, handle)
        if registry.state(row) == "active":
            registry.detach_tenant(reg, handle)
            log("  detached")
        if registry.state(_find(reg, handle)) == "detached":
            registry.purge_tenant(reg, handle)
            log("  purged")
    except registry.RegistryError as e:
        log(f"  partial: {e}")
        return EXIT_PARTIAL
    return EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mtg-erase", description=__doc__.split("\n\n")[0])
    ap.add_argument("handle")
    ap.add_argument("--confirm", required=True, help="repeat the handle exactly; erasure is irreversible")
    ap.add_argument("--dest", default=None, help="Zone URI (default: MTGC_LAKE_TENANT_URI)")
    args = ap.parse_args(argv)
    try:
        if args.confirm != args.handle:
            raise registry.RegistryError("--confirm must repeat the handle exactly")
        uri = args.dest or os.environ.get("MTGC_LAKE_TENANT_URI")
        if not uri:
            raise shipper.ZoneError("no zone: pass --dest or set MTGC_LAKE_TENANT_URI")
        zone = shipper.Zone(uri)
        with closing(registry.open_registry(create=False)) as reg, closing(shipper.open_state()) as state:
            code = erase(reg, state, zone, args.handle)
    except (shipper.ZoneError, registry.RegistryError, lake_keys.LakeKeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        code = EXIT_ERROR
    sys.exit(code)


if __name__ == "__main__":
    main()
