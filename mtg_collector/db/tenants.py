"""Which user databases exist on this box, and the offline job that walks them.

Single-tenant mode (no registry.sqlite) is one tenant: the configured database.
Multi-tenant mode lists the registry's active users, each at
`$MTGC_HOME/tenants/<database_id>.sqlite`.  O(tenants) work runs here, offline,
never inside a request or a catalog refresh (D7/D8): a failure on one tenant is
reported and skipped, never silently turned into "did one tenant".
"""

import sqlite3
from pathlib import Path

from mtg_collector.utils import get_mtgc_home

PARTIAL_EXIT = 2


def registry_path() -> Path:
    return get_mtgc_home() / "registry.sqlite"


def tenant_path(database_id: str) -> Path:
    return get_mtgc_home() / "tenants" / f"{database_id}.sqlite"


def list_tenants(db_path: str) -> list[tuple[str, str]]:
    """(label, file) for every active tenant; the one configured DB without a registry."""
    reg = registry_path()
    if not reg.exists():
        return [("single", db_path)]
    conn = sqlite3.connect(f"file:{reg}?mode=ro", uri=True)
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT database_id FROM user WHERE retired_at IS NULL ORDER BY database_id"
        )]
    finally:
        conn.close()
    return [(i, str(tenant_path(i))) for i in ids]


def _shared_for_tenants() -> str | None:
    """The catalogue every tenant file must be opened against.

    Multi-tenant mode: `$MTGC_HOME/shared.sqlite`, required.  The server pins it into
    MTGC_SHARED_DB at startup, but a chain unit is a one-off process that starts with
    only its env file, so without this a tenant opens as a monolithic database and
    `init_db` reports every catalogue object missing from it.
    """
    from mtg_collector.db.connection import get_shared_db_path
    from mtg_collector.tenancy import paths as tenant_paths

    if not registry_path().exists():
        return get_shared_db_path()
    shared = tenant_paths.shared_file()
    if not shared.exists():
        raise FileNotFoundError(f"multi-tenant mode needs the shared catalogue at {shared}")
    return str(shared)


def rebuild_growth_all(db_path: str, *, rebuild=None, open_tenant=None) -> int:
    """Rebuild every tenant's growth series.  Returns 0, or PARTIAL_EXIT if any failed.

    `rebuild` / `open_tenant` are seams for tests; the defaults are the real ones.
    """
    from mtg_collector.db.connection import open_connection
    from mtg_collector.db.growth import rebuild_history
    from mtg_collector.db.schema import init_db

    rebuild = rebuild or rebuild_history
    open_tenant = open_tenant or (lambda path: open_connection(path, _shared_for_tenants()))

    failed: list[tuple[str, str]] = []
    tenants = list_tenants(db_path)
    for label, path in tenants:
        try:
            conn = open_tenant(path)
            try:
                init_db(conn)
                days = rebuild(conn)
            finally:
                conn.close()
            print(f"  [{label}] collection value history: {days} day(s) materialized")
        except Exception as e:
            failed.append((label, f"{type(e).__name__}: {e}"))
            print(f"  [{label}] FAILED: {type(e).__name__}: {e}")
    if failed:
        print(f"PARTIAL: {len(tenants) - len(failed)}/{len(tenants)} tenants rebuilt; "
              f"failed: {', '.join(label for label, _ in failed)}")
        return PARTIAL_EXIT
    return 0
