"""Tenant data never crosses tenants through a shared cache (sp-4xp2ho).

A new tenant was served another tenant's collection with no request reaching
origin -- the signature of an edge cache keyed on the URL.  The origin cannot
configure the CDN, so it must make a crossing unrepresentable: tenant responses
are ``private, no-store`` and name the identity headers in ``Vary``.

This drives the real HTTP path (uvicorn on a socket, not the in-process route)
through a deliberately hostile cache: it stores every 200 regardless of
Cache-Control (an edge rule overriding the origin) and honours only ``Vary``.
"""

import http.client
import http.server
import threading

import pytest
import uvicorn

from mtg_collector import access
from mtg_collector.asgi_app import create_app
from mtg_collector.db import registry
from mtg_collector.tenancy import MultiTenantResolver
from tests.jwks_server import JwksServer
from tests.test_isolation_gate import STATIC

A_EMAIL = "alice@x.org"
B_EMAIL = "bobby@x.org"


@pytest.fixture(scope="module")
def jwks():
    with JwksServer() as server:
        yield server


@pytest.fixture
def origin(tmp_path, monkeypatch, jwks):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    reg = registry.open_registry()
    registry.create_tenant(reg, "alice")
    registry.create_tenant(reg, "bobby")
    registry.add_identity(reg, "alice", A_EMAIL)
    registry.add_identity(reg, "bobby", B_EMAIL)
    reg.close()
    verifier = access.AccessVerifier(access.load_config(jwks.env))
    app = create_app(None, STATIC, str(tmp_path / "legacy.sqlite"),
                     resolver=MultiTenantResolver(verifier), multi=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield port
    server.should_exit = True
    thread.join(10)


def _caching_proxy(origin_port, honour_vary):
    store = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            ident = self.headers.get(access.HEADER, "")
            conn = http.client.HTTPConnection("127.0.0.1", origin_port)
            hit = None
            for (path, seen), entry in store.items():
                if path == self.path and (not honour_vary or seen == ident):
                    hit = entry
                    break
            if hit is None:
                conn.request("GET", self.path, headers={access.HEADER: ident})
                r = conn.getresponse()
                hit = (r.status, r.read(), r.getheader("Vary", ""))
                if r.status == 200:
                    # Stored despite Cache-Control, keyed per Vary only.
                    vary = hit[2].lower()
                    keyed = ident if "cf-access-jwt-assertion" in vary else ""
                    store[(self.path, keyed if honour_vary else "")] = hit
            self.send_response(hit[0])
            self.send_header("Content-Length", str(len(hit[1])))
            self.end_headers()
            self.wfile.write(hit[1])

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _get(port, path, headers):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", path, headers=headers)
    r = conn.getresponse()
    return r.status, r.read().decode(), r


def _post(port, path, body, headers):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("POST", path, body=body,
                 headers={**headers, "Content-Type": "application/json"})
    r = conn.getresponse()
    r.read()
    return r.status


def test_origin_marks_tenant_responses_uncacheable_and_identity_keyed(origin, jwks):
    ha = {access.HEADER: jwks.token(A_EMAIL)}
    for path in ("/api/binders", "/api/collection?q=", "/collection"):
        status, _, r = _get(origin, path, ha)
        assert status == 200, path
        assert r.getheader("Cache-Control") == "private, no-store", path
        vary = r.getheader("Vary").lower()
        assert "cookie" in vary and "cf-access-jwt-assertion" in vary, path
        assert r.getheader("ETag") is None, path


def test_consecutive_tenants_never_share_a_cached_response(origin, jwks):
    ha = {access.HEADER: jwks.token(A_EMAIL)}
    hb = {access.HEADER: jwks.token(B_EMAIL)}
    assert _post(origin, "/api/binders", '{"name": "alice-secret"}', ha) == 201

    proxy = _caching_proxy(origin, honour_vary=True)
    try:
        port = proxy.server_address[1]
        # control arm: the owner sees the data, and primes the cache
        _, body_a, _ = _get(port, "/api/binders", ha)
        assert "alice-secret" in body_a
        # same URL, next, from the other tenant
        status, body_b, _ = _get(port, "/api/binders", hb)
        assert status == 200
        assert "alice-secret" not in body_b
        assert body_b.strip() == "[]"
    finally:
        proxy.shutdown()
