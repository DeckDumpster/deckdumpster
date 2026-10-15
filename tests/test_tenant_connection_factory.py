"""Every route gets its tenant connection from one factory (sp-81wvug).

Static: nothing under mtg_collector/routes or asgi_app.py opens a database
itself. Dynamic: every native router family is driven as two tenants and each
request must open that tenant's own file.
"""

import ast
import re
from pathlib import Path

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from mtg_collector import access
from mtg_collector.asgi_app import create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db import registry
from mtg_collector.tenancy import MultiTenantResolver, connection, paths
from tests.jwks_server import JwksServer

PKG = Path(cps.__file__).resolve().parent.parent
STATIC = PKG / "static"
OPENERS = {"open_connection", "get_connection", "open_catalog_connection", "connect"}


def opener_calls(source):
    """Names of connection-opening calls in `source`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in OPENERS:
                found.append(name)
    return found


def _native_modules():
    return sorted(PKG.glob("routes/*.py")) + [PKG / "asgi_app.py"]


@pytest.mark.parametrize("path", _native_modules(), ids=lambda p: p.name)
def test_native_modules_open_no_connection_themselves(path):
    assert opener_calls(path.read_text()) == []


def test_the_check_sees_a_direct_open():
    # control arm: the reintroduced bug is what the check exists to catch
    src = "def get_conn():\n    return open_connection(db_path, shared)\n"
    assert opener_calls(src) == ["open_connection"]
    assert opener_calls("import sqlite3\nsqlite3.connect('x')") == ["connect"]


def test_the_legacy_handler_gets_its_connection_from_the_factory():
    src = Path(cps.__file__).read_text()
    body = src[src.index("    def _get_conn(self):"):src.index("    def do_GET")]
    assert opener_calls(body) == ["tenant_connection"]


@pytest.fixture(scope="module")
def jwks():
    with JwksServer() as server:
        yield server


def test_every_native_router_opens_the_requesting_tenants_file(tmp_path, monkeypatch, jwks):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    reg = registry.open_registry()
    ids = {"alice": registry.create_tenant(reg, "alice"), "bobby": registry.create_tenant(reg, "bobby")}
    registry.add_identity(reg, "alice", "alice@x.org")
    registry.add_identity(reg, "bobby", "bobby@x.org")
    reg.close()
    verifier = access.AccessVerifier(access.load_config(jwks.env))
    legacy = str(tmp_path / "legacy.sqlite")
    app = create_app(None, STATIC, legacy, resolver=MultiTenantResolver(verifier), multi=True)

    opened = []
    real = connection.open_connection

    def spy(path, *a, **kw):
        opened.append(path)
        return real(path, *a, **kw)

    monkeypatch.setattr(connection, "open_connection", spy)
    client = TestClient(app, raise_server_exceptions=False)
    native = [r for r in app.routes
              if getattr(r, "endpoint", None) is not None and not isinstance(r, Route)
              or type(r).__name__ == "APIRoute"]
    native = [r for r in native if r.path != "/{path:path}"]
    assert len(native) >= 10  # positive control: the routers were found
    families = {r.endpoint.__module__ for r in native}
    assert "mtg_collector.routes.collection" in families

    for family in families:
        routes = [r for r in native if r.endpoint.__module__ == family]
        for handle, email in (("alice", "alice@x.org"), ("bobby", "bobby@x.org")):
            expect = str(paths.tenant_db_file(ids[handle]))
            hit = 0
            for r in routes:
                url = re.sub(r"\{[^}:]+(:int)?\}", "1", r.path)
                for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
                    opened.clear()
                    client.request(method, url, json={}, headers={access.HEADER: jwks.token(email)})
                    assert set(opened) <= {expect}, (family, method, url, opened)
                    hit += bool(opened)
            assert hit, f"{family} opened no connection as {handle}"
