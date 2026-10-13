"""Tenant lifecycle: mtg tenant create|list|rename|detach|reattach|purge|adopt|migrate|set-key|identity"""

import sys

from mtg_collector.db import registry
from mtg_collector.tenancy import keycrypt, paths


def register(subparsers):
    p = subparsers.add_parser("tenant", help="Manage tenants (multi-tenant mode)")
    sub = p.add_subparsers(dest="tenant_command", metavar="<subcommand>")

    s = sub.add_parser("create", help="Create a tenant with an empty database")
    s.add_argument("handle")
    s.set_defaults(func=run_create)

    s = sub.add_parser("list", help="List tenants")
    s.set_defaults(func=run_list)

    s = sub.add_parser("rename", help="Change an active tenant's handle")
    s.add_argument("handle")
    s.add_argument("new_handle")
    s.set_defaults(func=run_rename)

    s = sub.add_parser("detach", help="Make a tenant unreachable; its files stay")
    s.add_argument("handle")
    s.set_defaults(func=run_detach)

    s = sub.add_parser("reattach", help="Bring a detached tenant back")
    s.add_argument("handle")
    s.add_argument("--as", dest="as_handle", help="Handle to come back under, if the old one is taken")
    s.set_defaults(func=run_reattach)

    s = sub.add_parser("purge", help="Delete a detached tenant's files and key")
    s.add_argument("handle")
    s.add_argument("--confirm", required=True, metavar="HANDLE",
                   help="Repeat the handle to confirm irreversible deletion")
    s.set_defaults(func=run_purge)

    s = sub.add_parser("adopt", help="Register a copy of an existing database as a tenant")
    s.add_argument("handle")
    s.add_argument("source", help="Path to an existing collection.sqlite")
    s.set_defaults(func=run_adopt)

    s = sub.add_parser("migrate", help="Bring tenant databases to the current schema")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("handle", nargs="?")
    g.add_argument("--all", action="store_true", help="Every active tenant, each reported")
    s.set_defaults(func=run_migrate)

    s = sub.add_parser("set-key", help="Store a tenant's Anthropic API key (read from stdin)")
    s.add_argument("handle")
    s.set_defaults(func=run_set_key)

    s = sub.add_parser("generate-master-key", help="Print a new master key for tenant secrets")
    s.set_defaults(func=lambda a: print(keycrypt.generate_master_key()))

    ident = sub.add_parser("identity", help="Bind verified emails to tenants")
    isub = ident.add_subparsers(dest="identity_command", metavar="<subcommand>")
    s = isub.add_parser("add", help="Bind an email to a tenant")
    s.add_argument("handle")
    s.add_argument("email")
    s.set_defaults(func=run_identity_add)
    s = isub.add_parser("list", help="List active bindings")
    s.add_argument("handle", nargs="?")
    s.set_defaults(func=run_identity_list)
    s = isub.add_parser("remove", help="Unbind an email")
    s.add_argument("email")
    s.set_defaults(func=run_identity_remove)
    ident.set_defaults(func=lambda a: ident.print_help())

    p.set_defaults(func=lambda a: p.print_help())


def _guarded(fn):
    def run(args):
        try:
            with _registry() as conn:
                fn(conn, args)
        except (registry.RegistryError, paths.InvalidHandle, keycrypt.MasterKeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
    return run


class _registry:
    def __enter__(self):
        self.conn = registry.open_registry()
        return self.conn

    def __exit__(self, *exc):
        self.conn.close()
        return False


def _create(conn, args):
    database_id = registry.create_tenant(conn, args.handle)
    print(f"created {args.handle} -> {database_id}")


def _list(conn, args):
    rows = registry.list_tenants(conn)
    if not rows:
        print("no tenants")
        return
    print(f"{'HANDLE':<34}{'DATABASE_ID':<28}{'STATE':<10}{'IDENTITIES':<11}KEY")
    for r in rows:
        print(f"{r['handle']:<34}{r['database_id']:<28}{registry.state(r):<10}"
              f"{r['identities']:<11}{'yes' if r['has_key'] else 'no'}")


def _rename(conn, args):
    registry.rename_tenant(conn, args.handle, args.new_handle)
    print(f"renamed {args.handle} -> {args.new_handle}")


def _detach(conn, args):
    database_id = registry.detach_tenant(conn, args.handle)
    print(f"detached {args.handle} ({database_id}); files kept")


def _reattach(conn, args):
    database_id = registry.reattach_tenant(conn, args.handle, as_handle=args.as_handle)
    print(f"reattached {args.as_handle or args.handle} ({database_id})")


def _purge(conn, args):
    if args.confirm != args.handle:
        raise registry.RegistryError("--confirm must repeat the handle exactly")
    database_id = registry.purge_tenant(conn, args.handle)
    print(f"purged {args.handle} ({database_id})")


def _adopt(conn, args):
    database_id = registry.adopt_database(conn, args.handle, args.source)
    print(f"adopted {args.source} as {args.handle} -> {database_id}")


def _migrate(conn, args):
    if args.all:
        targets = [r for r in registry.list_tenants(conn) if registry.state(r) == "active"]
    else:
        targets = [registry.find_tenant(conn, args.handle)]
    failed = 0
    for r in targets:
        try:
            before, after = registry.migrate_tenant(r["database_id"])
            print(f"{r['handle']} ({r['database_id']}): schema {before} -> {after}")
        except Exception as exc:
            failed += 1
            print(f"{r['handle']} ({r['database_id']}): FAILED: {exc}", file=sys.stderr)
    if not targets:
        print("no active tenants")
    if failed:
        sys.exit(1)


def _set_key(conn, args):
    secret = sys.stdin.read().strip()
    if not secret:
        raise registry.RegistryError("no key on stdin")
    registry.set_tenant_key(conn, args.handle, secret)
    print(f"stored key for {args.handle}")


def _identity_add(conn, args):
    registry.add_identity(conn, args.handle, args.email)
    print(f"bound {args.email.strip().lower()} -> {args.handle}")


def _identity_list(conn, args):
    for r in registry.list_identities(conn, args.handle):
        print(f"{r['email']:<40}{r['handle']:<34}{r['database_id']}")


def _identity_remove(conn, args):
    registry.remove_identity(conn, args.email)
    print(f"unbound {args.email.strip().lower()}")


run_create = _guarded(_create)
run_list = _guarded(_list)
run_rename = _guarded(_rename)
run_detach = _guarded(_detach)
run_reattach = _guarded(_reattach)
run_purge = _guarded(_purge)
run_adopt = _guarded(_adopt)
run_migrate = _guarded(_migrate)
run_set_key = _guarded(_set_key)
run_identity_add = _guarded(_identity_add)
run_identity_list = _guarded(_identity_list)
run_identity_remove = _guarded(_identity_remove)
