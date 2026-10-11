"""The collection family is served by native FastAPI routes (multi-tenancy N3)."""

import gzip

import pytest
from starlette.testclient import TestClient

from mtg_collector.asgi_app import create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db.connection import get_connection
from mtg_collector.db.schema import init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "c.sqlite"
    conn = get_connection(str(db))
    init_db(conn)
    conn.close()
    static = tmp_path / "static"
    static.mkdir()

    def legacy_hit(self):
        raise AssertionError(f"legacy handler reached for {self.command} {self.path}")

    for verb in ("do_GET", "do_POST", "do_PUT", "do_DELETE"):
        monkeypatch.setattr(cps.CrackPackHandler, verb, legacy_hit)
    return TestClient(create_app(None, static, str(db)), raise_server_exceptions=False)


def test_listing_and_search_alias_are_native_and_identical(client):
    a = client.get("/api/collection")
    b = client.get("/api/search")
    assert a.status_code == 200 and a.json() == b.json()
    assert a.json()["rows"] == [] and a.json()["total"] == 0
    assert a.headers["cache-control"] == "private, no-cache"


def test_bad_page_params_are_a_400_not_a_clamp(client):
    r = client.get("/api/collection?limit=0")
    assert r.status_code == 400 and "limit" in r.json()["error"]


def test_search_error_carries_position(client):
    r = client.get("/api/collection", params={"q": "mv:("})
    assert r.status_code == 400 and "position" in r.json()


def test_copies_requires_printing_id(client):
    r = client.get("/api/collection/copies")
    assert r.status_code == 400 and r.json() == {"error": "printing_id required"}
    assert client.get("/api/collection/copies?printing_id=x").json() == []


def test_growth_unfiltered_is_native(client):
    assert client.get("/api/collection/growth").status_code == 200


def test_history_of_nothing_is_empty(client):
    r = client.get("/api/collection/7/history")
    assert r.json() == {"status_history": [], "movement_history": [], "combined": []}


def test_etag_revalidates_and_gzip_varies_the_tag(client):
    r = client.get("/api/collection")
    again = client.get("/api/collection", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    assert r.headers["vary"] == "Accept-Encoding"


def test_gzip_is_negotiated(client):
    r = client.get("/api/collection/growth", headers={"Accept-Encoding": "gzip"})
    if r.headers.get("content-encoding") == "gzip":
        assert r.headers["etag"].endswith('-gzip"')
        gzip.decompress(r.content)  # TestClient already decoded; must not raise below
    assert r.status_code == 200


@pytest.mark.parametrize("path", [
    "/api/collection",
    "/api/collection/bulk-delete",
])
def test_invalid_json_body_is_a_400(client, path):
    r = client.post(path, content=b"{not json")
    assert r.status_code == 400 and r.json() == {"error": "Invalid JSON"}


def test_invalid_json_on_put_and_dispose(client):
    assert client.put("/api/collection/1", content=b"x").status_code == 400
    assert client.post("/api/collection/1/dispose", content=b"x").status_code == 400


def test_bulk_delete_and_dispose_validate(client):
    assert client.post("/api/collection/bulk-delete", json={}).json() == {
        "error": "ids array required"}
    assert client.post("/api/collection/1/dispose", json={}).json() == {
        "error": "new_status required"}


def test_add_requires_printing_id(client):
    r = client.post("/api/collection", json={})
    assert r.status_code == 400 and r.json() == {"error": "printing_id is required"}


def test_update_missing_entry_is_404(client):
    assert client.put("/api/collection/99", json={"condition": "NM"}).status_code == 404


def test_delete_needs_confirm_then_404s_for_missing(client):
    assert client.delete("/api/collection/99").json() == {"error": "Must pass ?confirm=true"}
    assert client.delete("/api/collection/99?confirm=true").status_code == 404


def test_receive_missing_entry_reports_zero(client):
    assert client.post("/api/collection/99/receive").json() == {"received": 0}


def test_non_numeric_id_falls_through_to_the_legacy_adapter(client):
    r = client.get("/api/collection/abc")
    assert r.status_code == 500  # legacy_hit fixture raised: it was the adapter
