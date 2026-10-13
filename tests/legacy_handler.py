"""A CrackPackHandler for tests that drive it on a bare socket.

The front door's middleware binds the tenant for a real request; a test that
serves the handler from ThreadingHTTPServer threads has no middleware, and a
server thread does not inherit the test's binding. This binds one per request.
"""

from mtg_collector.cli.crack_pack_server import CrackPackHandler
from mtg_collector.tenancy import SingleTenantResolver, bind


class BoundCrackPackHandler(CrackPackHandler):
    def handle(self):
        with bind(SingleTenantResolver().resolve(None)):
            super().handle()


def bare_handler():
    """A CrackPackHandler with no socket, for tests that call one `_api_*` method.

    The one constructor for such handlers: ``object.__new__(CrackPackHandler)``
    written out at a call site skips ``__init__`` and says nothing about which
    tenant the handler answers for. This refuses to build one outside a bound
    tenant (the autouse ``_single_tenant_bound`` fixture binds the single-tenant
    one), so a handler can never reach ``_get_conn()`` without a resolved tenant.
    """
    from mtg_collector.tenancy import current_tenant

    current_tenant()
    return CrackPackHandler.__new__(CrackPackHandler)
