"""mtg lake ship|readback|backfill|resolve-gap|check: the tenant zone's shipper and read-back (lakehouse 11)."""

import os
import sqlite3
import sys
from datetime import datetime, timezone

from mtg_collector.db import registry
from mtg_collector.lake import crypto, shipper
from mtg_collector.lake import keys as lake_keys
from mtg_collector.tenancy import paths


def register(subparsers):
    p = subparsers.add_parser("lake", help="Tenant zone: ship holdings, read back, check")
    sub = p.add_subparsers(dest="lake_command", metavar="<subcommand>")

    s = sub.add_parser("ship", help="Ship the outbox, then read back. Exit 3 on a gap, 2 on a partial night")
    s.add_argument("--dest", default=None, help="Zone URI (default: MTGC_LAKE_TENANT_URI)")
    s.add_argument("--tenant", default=None, help="One database_id (default: every active tenant)")
    s.add_argument("--no-readback", action="store_true")
    s.set_defaults(func=run_ship)
    s = sub.add_parser("readback", help="Rebuild zone_holdings from the zone alone")
    s.add_argument("--dest", default=None)
    s.add_argument("--tenant", default=None)
    s.set_defaults(func=run_readback)
    s = sub.add_parser("backfill", help="Append every current row to the outbox, once per tenant")
    s.add_argument("--tenant", default=None)
    s.add_argument("--again", action="store_true")
    s.set_defaults(func=run_backfill)
    s = sub.add_parser("resolve-gap", help="Repair open gaps by re-emitting current state (run readback first)")
    s.add_argument("--tenant", default=None)
    s.set_defaults(func=run_resolve_gap)
    s = sub.add_parser("check", help="Three-number check: outbox = shipped = read back. Exit 1 if not")
    s.add_argument("--tenant", default=None)
    s.set_defaults(func=run_check)
    s = sub.add_parser(
        "value", help="Value every tenant from the zone and Iceberg prices; --compare checks the online series, else writes")
    s.add_argument("--tenant", default=None)
    s.add_argument("--compare", action="store_true",
                   help="Compare with the online series; write nothing. Exit 1 on any disagreement")
    s.set_defaults(func=run_value)
    p.set_defaults(func=lambda a: p.print_help())


def _open_tenant(database_id):
    return sqlite3.connect(str(paths.tenant_db_file(database_id)), timeout=30.0, isolation_level=None)


def _zone(args):
    uri = args.dest or os.environ.get("MTGC_LAKE_TENANT_URI")
    if not uri:
        raise shipper.ZoneError("no zone: pass --dest or set MTGC_LAKE_TENANT_URI")
    return shipper.Zone(uri)


def _guarded(fn):
    def run(args):
        try:
            code = fn(args)
        except (shipper.ZoneError, crypto.LakeCryptoError, registry.RegistryError, lake_keys.LakeKeyError) as e:
            print(f"error: {e}", file=sys.stderr)
            code = shipper.EXIT_ERROR
        sys.exit(code or 0)
    return run


def _ids(reg, args):
    return [args.tenant] if args.tenant else shipper.active_ids(reg)


def _walk(args, *, ship, readback):
    master = crypto.load_master_key(crypto.master_key_path())
    zone = _zone(args)
    with closing_registry() as reg:
        return shipper.run_all(
            reg, shipper.open_state(), zone, master=master, open_tenant=_open_tenant,
            as_of=datetime.now(timezone.utc).date().isoformat(), ids=_ids(reg, args),
            do_ship=ship, do_readback=readback)


def closing_registry():
    from contextlib import closing
    return closing(registry.open_registry(create=False))


@_guarded
def run_ship(args):
    return _walk(args, ship=True, readback=not args.no_readback)


@_guarded
def run_readback(args):
    return _walk(args, ship=False, readback=True)


@_guarded
def run_backfill(args):
    state = shipper.open_state()
    with closing_registry() as reg:
        for i in _ids(reg, args):
            t = _open_tenant(i)
            try:
                print(f"  [{i}] emitted {shipper.backfill(t, state, i, again=args.again)} row(s)")
            finally:
                t.close()


@_guarded
def run_resolve_gap(args):
    state = shipper.open_state()
    with closing_registry() as reg:
        for i in _ids(reg, args):
            t = _open_tenant(i)
            try:
                print(f"  [{i}] resolved; appended {shipper.resolve_gap(t, state, i)} outbox row(s)")
            finally:
                t.close()


@_guarded
def run_check(args):
    state = shipper.open_state()
    bad = False
    with closing_registry() as reg:
        for i in _ids(reg, args):
            t = _open_tenant(i)
            try:
                c = shipper.check_tenant(t, state, i)
            finally:
                t.close()
            bad |= not c.ok
            print(f"  [{i}] outbox={c.outbox} shipped={c.shipped} read_back={c.read_back} "
                  f"pending={c.pending} fold={'equal' if c.folded_equal else 'DIFFERS'} "
                  f"gaps={len(c.open_gaps)} {'OK' if c.ok else 'FAIL'}")
    return shipper.EXIT_ERROR if bad else 0


@_guarded
def run_value(args):
    """Offline valuation (lakehouse 12).  One tenant's failure never stops the others."""
    from mtg_collector.db.connection import get_shared_db_path, open_connection
    from mtg_collector.db.growth import UNFILTERED_WHERE, series_rows
    from mtg_collector.lake import iceberg_prices, valuation

    shared = get_shared_db_path()
    if not shared:
        raise shipper.ZoneError("no catalogue: MTGC_SHARED_DB is unset or missing")
    catalog = iceberg_prices.open_catalog(os.environ["MTGC_LAKE_CATALOG"], os.environ["MTGC_LAKE_WAREHOUSE"])
    work = valuation.open_work(shared)
    n = valuation.load_prices(work, catalog.load_table(iceberg_prices.PRICES))
    print(f"  loaded {n} price row(s)")
    state = shipper.open_state()
    failed, differ = [], []
    with closing_registry() as reg:
        ids = _ids(reg, args)
    for i in ids:
        try:
            tenant = open_connection(str(paths.tenant_db_file(i)), shared)
            try:
                if args.compare:
                    left = valuation.pending(tenant, state, i)
                    if left:
                        differ.append(i)
                        print(f"  [{i}] NOT COMPARABLE: {left} outbox row(s) not yet shipped")
                        continue
                    offline = valuation.series(work, valuation.holdings(state, i))
                    online = series_rows(tenant, where_sql=UNFILTERED_WHERE, params=[])
                    c = valuation.compare_rows(i, offline, online)
                    if c.agree:
                        print(f"  [{i}] AGREE over {c.days_offline} day(s)")
                    else:
                        differ.append(i)
                        print(f"  [{i}] DIFFER on {len(c.differing)} point(s); first: {c.differing[0]}")
                else:
                    days = valuation.store(tenant, valuation.series(work, valuation.holdings(state, i)))
                    print(f"  [{i}] collection value history: {days} day(s) written")
            finally:
                tenant.close()
        except Exception as e:
            failed.append(i)
            print(f"  [{i}] FAILED: {type(e).__name__}: {e}")
    if differ:
        return shipper.EXIT_ERROR
    if failed:
        print(f"PARTIAL: {len(ids) - len(failed)}/{len(ids)} tenants; failed: {', '.join(failed)}")
        return shipper.EXIT_PARTIAL
    return 0
