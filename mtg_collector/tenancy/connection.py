"""The one factory a request gets its tenant database connection from.

Native routers and the legacy handler both call `tenant_connection`; neither
may call `open_connection` on a path of its own. In multi-tenant mode the
tenant's id names its file; a router that opened the server's single
`db_path` served every tenant the legacy owner's collection (sp-81wvug).
`tests/test_tenant_connection_factory.py` fails any module under
`mtg_collector/routes` or the ASGI app that opens a connection itself.
"""

from mtg_collector.access import multitenant_enabled
from mtg_collector.db.connection import open_connection
from mtg_collector.tenancy import paths as tenant_paths
from mtg_collector.tenancy.context import current_tenant


def tenant_connection(default_db_path, shared_path, *, wal=True):
    # current_tenant() raises outside a resolved request: no answer without one.
    tenant = current_tenant()
    db_path = default_db_path
    if multitenant_enabled():
        db_path = str(tenant_paths.tenant_db_file(tenant.value))
    return open_connection(db_path, shared_path, wal=wal)
