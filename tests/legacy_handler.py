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
