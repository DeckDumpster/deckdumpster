"""Tenant lifecycle: mtg tenant create|list|rename|detach|reattach|purge|adopt|migrate|set-key|identity|lake-key"""

import base64
import os
import sys

from mtg_collector.db import registry
from mtg_collector.lake import crypto
from mtg_collector.lake import keys as lake_keys
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

    s = sub.add_parser("legacy-migrate", help="Copy a pre-tenancy database onto a ULID tenant (source untouched)")
    s.add_argument("handle")
    s.add_argument("source", help="Path to the legacy collection.sqlite")
    s.add_argument("--legacy-shared", help="The legacy split deployment's shared.sqlite, if it had one")
    s.add_argument("--check-space", action="store_true", help="Only check free space (run before stopping production)")
    s.set_defaults(func=run_legacy_migrate)

    s = sub.add_parser("import-archive", help="Import an export-install archive as a new tenant, images included")
    s.add_argument("archive")
    s.add_argument("--handle", required=True)
    s.add_argument("--email", required=True)
    s.add_argument("--dry-run", action="store_true", help="Rehearse against a scratch home; production untouched")
    s.set_defaults(func=run_import_archive)

    s = sub.add_parser("legacy-rollback", help="Detach a migrated tenant so the legacy database serves again")
    s.add_argument("handle")
    s.set_defaults(func=run_legacy_rollback)

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

    lk = sub.add_parser("lake-key", help="Lake (tenant zone) key custody: init, backup, register, tombstone, status")
    lsub = lk.add_subparsers(dest="lake_key_command", metavar="<subcommand>")
    s = lsub.add_parser("init", help="Mint the lake master key file (refuses to overwrite)")
    s.set_defaults(func=run_lake_init)
    s = lsub.add_parser("backup", help="Print the lake master key for the password manager")
    s.add_argument("--yes", action="store_true", help="acknowledge this prints secret material")
    s.set_defaults(func=run_lake_backup)
    s = lsub.add_parser("register", help="Make tenants' lake keys derivable (one database_id, or --all active)")
    s.add_argument("database_id", nargs="?")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=run_lake_register)
    s = lsub.add_parser("tombstone", help="Revoke a tenant's lake key permanently")
    s.add_argument("database_id")
    s.add_argument("--reason", required=True)
    s.add_argument("--yes", action="store_true", help="acknowledge a tombstone is terminal")
    s.set_defaults(func=run_lake_tombstone)
    s = lsub.add_parser("status", help="Key state per database_id, and the master key fingerprint")
    s.set_defaults(func=run_lake_status)
    lk.set_defaults(func=lambda a: lk.print_help())

    p.set_defaults(func=lambda a: p.print_help())


def _guarded(fn):
    def run(args):
        try:
            with _registry() as conn:
                fn(conn, args)
        except (registry.RegistryError, paths.InvalidHandle, keycrypt.MasterKeyError, crypto.LakeCryptoError, lake_keys.LakeKeyError) as exc:
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


def _legacy_migrate(conn, args):
    from mtg_collector.tenancy import upgrade

    if args.check_space:
        upgrade.refuse_if_no_space(args.source, args.legacy_shared)
        print(f"enough free space for {args.source} ({upgrade.required_bytes(args.source, args.legacy_shared) / upgrade.GIB:.1f} G needed)")
        return
    database_id, outcome = upgrade.migrate_legacy(
        conn, args.handle, args.source, legacy_shared=args.legacy_shared,
        report=lambda line: print(f"  {line}", flush=True),
    )
    print(f"{outcome}: {args.handle} -> {database_id}; {args.source} was not modified")


def _import_archive(conn, args):
    from mtg_collector.tenancy import archive

    database_id = archive.import_archive(
        args.archive, args.handle, args.email, dry_run=args.dry_run,
        report=lambda line: print(f"  {line}", flush=True),
    )
    print(f"{'dry run ok (nothing kept)' if args.dry_run else 'imported'}: {args.handle} -> {database_id}")


def _legacy_rollback(conn, args):
    from mtg_collector.tenancy import upgrade

    database_id, outcome = upgrade.rollback_legacy(conn, args.handle)
    print(f"{outcome}: {args.handle} ({database_id}); files kept, legacy database serves again")


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


def _lake_init(conn, args):
    path = crypto.master_key_path()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise crypto.LakeCryptoError(
            f"{path} exists; overwriting the lake master key destroys every tenant's derived key. "
            "Move it aside by hand if that is what you mean."
        ) from None
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(crypto.generate_master_key() + "\n")
    print(f"wrote {path} (mode 600); fingerprint {crypto.fingerprint(crypto.load_master_key(path))}")
    print("BACK IT UP NOW: `mtg tenant lake-key backup --yes` into the password manager. "
          "A lost key is not a deleted tenant.")


def _lake_backup(conn, args):
    if not args.yes:
        raise crypto.LakeCryptoError("this prints secret material; pass --yes")
    master = crypto.load_master_key(crypto.master_key_path())
    print(base64.urlsafe_b64encode(master).decode("ascii"))


def _lake_register(conn, args):
    if bool(args.database_id) == bool(args.all):
        raise registry.RegistryError("name one database_id, or pass --all")
    ids = [args.database_id] if args.database_id else [
        r["database_id"] for r in registry.list_tenants(conn) if r["retired_at"] is None]
    for i in ids:
        paths.validate_database_id(i)
        lake_keys.register(conn, i)
        print(f"registered {i}")


def _lake_tombstone(conn, args):
    if not args.yes:
        raise registry.RegistryError("a tombstone is terminal; pass --yes")
    paths.validate_database_id(args.database_id)
    lake_keys.tombstone(conn, args.database_id, args.reason)
    print(f"tombstoned {args.database_id}")


def _lake_status(conn, args):
    path = crypto.master_key_path()
    print(f"master {path} fingerprint {crypto.fingerprint(crypto.load_master_key(path))}")
    for r in conn.execute("SELECT database_id, state, reason FROM lake_tenant_key ORDER BY database_id"):
        print(f"{r['database_id']}  {r['state']}  {r['reason'] or ''}".rstrip())


run_create = _guarded(_create)
run_list = _guarded(_list)
run_rename = _guarded(_rename)
run_detach = _guarded(_detach)
run_reattach = _guarded(_reattach)
run_purge = _guarded(_purge)
run_adopt = _guarded(_adopt)
run_migrate = _guarded(_migrate)
run_legacy_migrate = _guarded(_legacy_migrate)
run_import_archive = _guarded(_import_archive)
run_legacy_rollback = _guarded(_legacy_rollback)
run_set_key = _guarded(_set_key)
run_identity_add = _guarded(_identity_add)
run_identity_list = _guarded(_identity_list)
run_identity_remove = _guarded(_identity_remove)
run_lake_init = _guarded(_lake_init)
run_lake_backup = _guarded(_lake_backup)
run_lake_register = _guarded(_lake_register)
run_lake_tombstone = _guarded(_lake_tombstone)
run_lake_status = _guarded(_lake_status)
