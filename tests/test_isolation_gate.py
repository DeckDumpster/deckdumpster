"""The isolation gate (multi-tenancy bead 11, sp-0knuwi).

Tier 1 — no container. Two real tenants with real files, a real JWKS server, and
the real ASGI front door driven in-process. Every proof has a control arm: the
same request that is refused for the other tenant succeeds for the owner, so a
test that passed because nothing was there to find cannot pass.

Covered here: the cross-tenant data proof (read, write, delete), the image proof,
the leftover-header escalation proof, the ratchet of authenticated routes, and
the cache-header enumeration. The JWT negative list lives in
test_access_identity.py; deploy/handles.sh runs the same shapes against a real
container.
"""

import re
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mtg_collector import access
from mtg_collector.asgi_app import PUBLIC_ROUTES, create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.cli.page_routes import PAGE_ROUTES
from mtg_collector.db import registry
from mtg_collector.tenancy import MultiTenantResolver, images, paths
from tests.jwks_server import JwksServer

STATIC = Path(cps.__file__).resolve().parent.parent / "static"
A_EMAIL = "alice@x.org"
B_EMAIL = "bobby@x.org"


@pytest.fixture(scope="module")
def jwks():
    with JwksServer() as server:
        yield server


@pytest.fixture
def world(tmp_path, monkeypatch, jwks):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    reg = registry.open_registry()
    a = registry.create_tenant(reg, "alice")
    b = registry.create_tenant(reg, "bobby")
    registry.add_identity(reg, "alice", A_EMAIL)
    registry.add_identity(reg, "bobby", B_EMAIL)
    reg.close()
    verifier = access.AccessVerifier(access.load_config(jwks.env))
    app = create_app(None, STATIC, str(tmp_path / "legacy.sqlite"),
                     resolver=MultiTenantResolver(verifier), multi=True)
    return type("World", (), {
        "client": TestClient(app), "a": a, "b": b, "home": tmp_path,
        "ha": {access.HEADER: jwks.token(A_EMAIL)},
        "hb": {access.HEADER: jwks.token(B_EMAIL)},
        "jwks": jwks, "app": app,
    })


def _binder_names(db_file):
    conn = sqlite3.connect(db_file)
    try:
        return [r[0] for r in conn.execute("SELECT name FROM binders ORDER BY id")]
    finally:
        conn.close()


def _alice_binders(w, n=3):
    ids = []
    for i in range(n):
        r = w.client.post("/api/binders", json={"name": f"alice-{i}"}, headers=w.ha)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


# --- data: read, write, delete ------------------------------------------------

def test_data_written_by_one_tenant_lands_only_in_its_own_file(world):
    w = world
    _alice_binders(w)
    assert _binder_names(paths.tenant_db_file(w.a)) == ["alice-0", "alice-1", "alice-2"]
    assert _binder_names(paths.tenant_db_file(w.b)) == []


def test_b_cannot_read_a(world):
    w = world
    ids = _alice_binders(w)
    # control arm: the owner sees what B must not
    mine = w.client.get("/api/binders", headers=w.ha).json()
    assert len(mine) == 3
    assert w.client.get(f"/api/binders/{ids[-1]}", headers=w.ha).status_code == 200
    # B's own file is empty, so list is empty and A's highest id does not exist there
    theirs = w.client.get("/api/binders", headers=w.hb)
    assert theirs.status_code == 200 and theirs.json() == []
    assert w.client.get(f"/api/binders/{ids[-1]}", headers=w.hb).status_code == 404
    assert "alice" not in w.client.get("/api/binders", headers=w.hb).text


def test_b_cannot_write_a(world):
    w = world
    ids = _alice_binders(w)
    before = _binder_names(paths.tenant_db_file(w.a))
    r = w.client.put(f"/api/binders/{ids[0]}", json={"name": "hijacked"}, headers=w.hb)
    assert r.status_code == 404
    assert _binder_names(paths.tenant_db_file(w.a)) == before
    # control arm: the same request from the owner does write
    r = w.client.put(f"/api/binders/{ids[0]}", json={"name": "renamed"}, headers=w.ha)
    assert r.status_code == 200
    assert _binder_names(paths.tenant_db_file(w.a))[0] == "renamed"


def test_b_cannot_delete_a(world):
    w = world
    ids = _alice_binders(w)
    r = w.client.delete(f"/api/binders/{ids[-1]}", headers=w.hb)
    assert r.status_code == 404
    assert len(_binder_names(paths.tenant_db_file(w.a))) == 3
    # control arm
    assert w.client.delete(f"/api/binders/{ids[-1]}", headers=w.ha).status_code == 200
    assert len(_binder_names(paths.tenant_db_file(w.a))) == 2


# --- images ---------------------------------------------------------------------

def test_b_cannot_fetch_a_image(world):
    w = world
    (images.ingest_images_dir(w.a) / "a.jpg").write_bytes(b"alice-bytes")
    got = w.client.get("/api/ingest/image/a.jpg", headers=w.ha)
    assert got.status_code == 200 and got.content == b"alice-bytes"  # control arm
    assert w.client.get("/api/ingest/image/a.jpg", headers=w.hb).status_code == 404


def test_one_filename_two_tenants_two_files(world):
    w = world
    (images.ingest_images_dir(w.a) / "same.jpg").write_bytes(b"A")
    (images.ingest_images_dir(w.b) / "same.jpg").write_bytes(b"B")
    assert w.client.get("/api/ingest/image/same.jpg", headers=w.ha).content == b"A"
    assert w.client.get("/api/ingest/image/same.jpg", headers=w.hb).content == b"B"


@pytest.mark.parametrize("name", [
    "../{a}/ingest/a.jpg",
    "..%2F{a}%2Fingest%2Fa.jpg",
    "%2e%2e/{a}/ingest/a.jpg",
    "..\\{a}\\ingest\\a.jpg",
])
def test_b_cannot_reach_a_image_by_path(world, name):
    w = world
    (images.ingest_images_dir(w.a) / "a.jpg").write_bytes(b"alice-bytes")
    r = w.client.get("/api/ingest/image/" + name.format(a=w.a), headers=w.hb)
    assert r.status_code in (400, 404)
    assert b"alice-bytes" not in r.content


def test_no_image_is_served_from_the_pre_tenancy_global_dir(world):
    w = world
    legacy = w.home / "ingest_images"
    legacy.mkdir()
    (legacy / "old.jpg").write_bytes(b"global")
    for h in (w.ha, w.hb):
        assert w.client.get("/api/ingest/image/old.jpg", headers=h).status_code == 404


# --- identity cannot be steered by anything but the verified token --------------

@pytest.mark.parametrize("extra", [
    lambda w: {"X-MTGC-Tenant": w.a},
    lambda w: {"X-Tenant": w.a, "X-Tenant-Id": w.a},
    lambda w: {"Cf-Access-Authenticated-User-Email": A_EMAIL},
    lambda w: {"X-Forwarded-Email": A_EMAIL, "X-Forwarded-User": A_EMAIL},
    lambda w: {"X-Original-Url": f"/tenants/{w.a}.sqlite"},
])
def test_leftover_headers_do_not_escalate(world, extra):
    w = world
    _alice_binders(w)
    headers = {**w.hb, **extra(w)}
    assert w.client.get("/api/binders", headers=headers).json() == []
    # control arm: the same extra headers on no token get nothing at all
    assert w.client.get("/api/binders", headers=extra(w)).status_code == 401


def test_header_token_beats_cookie_token(world):
    w = world
    _alice_binders(w)
    w.client.cookies.set(access.COOKIE, w.jwks.token(A_EMAIL))
    assert w.client.get("/api/binders", headers=w.hb).json() == []
    w.client.cookies.clear()
    w.client.cookies.set(access.COOKIE, w.jwks.token(A_EMAIL))
    assert len(w.client.get("/api/binders").json()) == 3  # control arm


def test_a_detached_tenants_token_is_refused(world):
    w = world
    assert w.client.get("/api/binders", headers=w.hb).status_code == 200
    reg = registry.open_registry()
    registry.detach_tenant(reg, "bobby")
    reg.close()
    assert w.client.get("/api/binders", headers=w.hb).status_code == 403


# --- the ratchet of authenticated routes ----------------------------------------

_ROUTE_LITERAL = re.compile(r'path (?:==|\.startswith\() *"(/[^"]*)"')


def _declared_routes():
    src = Path(cps.__file__).read_text()
    routes = {m.group(1) for m in _ROUTE_LITERAL.finditer(src)}
    routes |= {r.path for r in PAGE_ROUTES}
    return sorted(routes)


def test_every_declared_route_demands_an_identity(world):
    w = world
    routes = _declared_routes()
    assert len(routes) > 90  # positive control: the extraction found the surface
    for method in ("GET", "POST", "PUT", "DELETE"):
        for route in routes:
            if route in PUBLIC_ROUTES:
                continue
            for headers in ({}, {access.HEADER: "garbage"}, {access.HEADER: w.jwks.token(A_EMAIL, aud=["x"])}):
                r = w.client.request(method, route, headers=headers)
                assert r.status_code == 401, f"{method} {route} -> {r.status_code}"


def test_unknown_paths_and_static_demand_an_identity_too(world):
    w = world
    for path in ("/static/shared.css", "/nope", "/api/nope", "/robots.txt", "/health/x"):
        assert w.client.get(path).status_code == 401, path


def test_public_routes_are_exactly_the_ops_probes():
    assert PUBLIC_ROUTES == ("/health", "/api/backup-status")


# --- caches ---------------------------------------------------------------------

_HASHED = re.compile(r"^/static/.+\.[0-9a-f]{16}\.[a-z0-9]+$")


def test_nothing_a_tenant_sees_is_publicly_cacheable_except_hashed_assets(world):
    w = world
    probed, assets = 0, set()
    for route in PAGE_ROUTES:
        if route.parametrized:
            continue
        r = w.client.get(route.path, headers=w.ha)
        probed += 1
        assert r.headers["cache-control"] == "private, no-store", route.path
        assert "etag" not in r.headers, route.path
        assets |= set(re.findall(r'(?:src|href)="(/static/[^"]+)"', r.text))
    assert probed > 15
    for url in ("/api/binders", "/api/sets", "/api/ingest2/counts", "/api/settings"):
        r = w.client.get(url, headers=w.ha)
        assert r.headers["cache-control"] == "private, no-store", url
    hashed = {a for a in assets if _HASHED.match(a)}
    assert hashed, "the pages name no content-addressed asset: the exemption is untested"
    for url in hashed:
        r = w.client.get(url, headers=w.ha)
        assert r.status_code == 200, url
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable", url
    # every other asset URL a page names is not public
    for url in assets - hashed:
        r = w.client.get(url, headers=w.ha)
        assert "public" not in r.headers.get("cache-control", ""), url


def test_control_arm_single_tenant_mode_does_serve_a_public_page(tmp_path, monkeypatch):
    # The leak the multi-tenant header ends is real: single mode still says public.
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_MULTITENANT", raising=False)
    r = TestClient(create_app(None, STATIC, str(tmp_path / "c.sqlite"))).get("/")
    assert r.headers["cache-control"] == "public, no-cache"


def test_refusals_are_private_no_store(world):
    w = world
    for r in (w.client.get("/collection"),
              w.client.get("/api/binders", headers={access.HEADER: w.jwks.token("nobody@x.org")})):
        assert r.status_code in (401, 403)
        assert r.headers["cache-control"] == "private, no-store"
