"""The ASGI front door and the tenant binding (multi-tenancy N3).

Tier 1 — no container, no network. The app is driven in-process through
Starlette's TestClient, so no port is bound.
"""

import contextvars
import sqlite3

import pytest
from starlette.testclient import TestClient

from mtg_collector.asgi_app import create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.tenancy import (
    NoTenantError,
    SingleTenantResolver,
    TenantId,
    current_tenant,
)


@pytest.fixture
def static_dir(tmp_path):
    d = tmp_path / "static"
    d.mkdir()
    (d / "home.html").write_text("<html>home</html>")
    return d


@pytest.fixture
def client(static_dir, tmp_path):
    app = create_app(None, static_dir, str(tmp_path / "c.sqlite"))
    return TestClient(app)


def test_tenant_id_cannot_be_constructed_by_a_caller():
    with pytest.raises(TypeError):
        TenantId("someone-else")


def test_current_tenant_raises_outside_a_request():
    with pytest.raises(NoTenantError):
        contextvars.Context().run(current_tenant)


def test_get_conn_raises_outside_a_request(tmp_path):
    db = tmp_path / "c.sqlite"
    sqlite3.connect(db).close()
    handler = object.__new__(cps.CrackPackHandler)
    handler.db_path = str(db)
    with pytest.raises(NoTenantError):
        contextvars.Context().run(handler._get_conn)


def test_single_tenant_resolver_always_returns_the_configured_tenant():
    r = SingleTenantResolver("only")
    assert r.resolve({}) == r.resolve({"path": "/x"})
    assert r.resolve({}).value == "only"


def test_request_runs_inside_a_bound_tenant(static_dir, tmp_path, monkeypatch):
    seen = []

    def spy(self):
        seen.append(current_tenant().value)
        self._send_json({"ok": True})

    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets", spy)
    app = create_app(None, static_dir, str(tmp_path / "c.sqlite"),
                     resolver=SingleTenantResolver("t1"))
    r = TestClient(app).get("/api/sets")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert seen == ["t1"]


def test_legacy_routes_pass_through_with_query_and_headers(client, monkeypatch):
    got = {}

    def spy(self, set_code, params):
        got["params"] = params
        got["accept"] = self.headers.get("Accept-Language")
        self._send_json({"n": 1})

    monkeypatch.setattr(cps.CrackPackHandler, "_api_set_browse", spy)
    r = client.get("/api/set-browse/xyz?q=t%3Acat&limit=5", headers={"Accept-Language": "xx"})
    assert r.status_code == 200
    assert got["params"] == {"q": ["t:cat"], "limit": ["5"]}
    assert got["accept"] == "xx"
    assert r.headers["cache-control"] == "private, no-cache"


def test_post_body_reaches_the_handler(client, monkeypatch):
    got = {}

    def spy(self):
        n = int(self.headers["Content-Length"])
        got["body"] = self.rfile.read(n)
        self._send_json({})

    monkeypatch.setattr(cps.CrackPackHandler, "do_POST", spy)
    r = client.post("/anything", content=b'{"a": 1}')
    assert r.status_code == 200
    assert got["body"] == b'{"a": 1}'


def test_a_page_is_served_with_its_cache_headers(client, monkeypatch):
    monkeypatch.setattr(
        cps.CrackPackHandler, "do_GET",
        lambda self: self._respond(b"<p>x</p>", "text/html", cps.CACHE_DOCUMENT),
    )
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["etag"]
    assert r.headers["cache-control"] == "public, no-cache"
    again = client.get("/", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""


def test_a_handler_crash_is_a_visible_500(client, monkeypatch):
    def boom(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(cps.CrackPackHandler, "do_GET", boom)
    c = TestClient(client.app, raise_server_exceptions=False)
    assert c.get("/x").status_code == 500


def test_sse_streams_through_without_content_length(client, monkeypatch):
    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b"event: a\ndata: 1\n\n")
        self.wfile.write(b"event: done\ndata: {}\n\n")

    monkeypatch.setattr(cps.CrackPackHandler, "do_GET", sse)
    r = client.get("/api/ingest2/process/1")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text == "event: a\ndata: 1\n\nevent: done\ndata: {}\n\n"


def test_there_are_no_framework_doc_routes(client):
    # /docs would shadow a legacy path; the adapter must see every path.
    paths = {getattr(r, "path", None) for r in client.app.routes}
    assert "/docs" not in paths and "/openapi.json" not in paths
