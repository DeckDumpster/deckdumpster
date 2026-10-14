"""The real server starts in multi-tenant mode against a migrated legacy fixture (sp-nm9s5u).

Prod cutover #2 crash-looped because startup recovery opened a tenant file
without the shared catalogue attached ("schema version N but 41 objects missing").
"""

import argparse
import sqlite3

import pytest
from starlette.testclient import TestClient

from mtg_collector import access
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db import registry
from mtg_collector.tenancy import keycrypt, upgrade
from tests.test_upgrade_path import _monolith


class _Identity:
    email = "ryan@example.com"


class _Verifier:
    def __init__(self, config):
        pass

    def verify(self, token):
        return _Identity()


def test_server_starts_multitenant_and_serves_the_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    for k in ("MTGC_DB", "MTGC_SHARED_DB"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    monkeypatch.setenv("MTGC_HTTP_PORT", "18080")
    monkeypatch.setenv("MTGC_ACCESS_TEAM_DOMAIN", "https://t.example.com")
    monkeypatch.setenv("MTGC_ACCESS_AUD", "aud")
    monkeypatch.setenv("MTGC_ACCESS_JWKS_URL", "https://t.example.com/certs")
    monkeypatch.setattr(access, "AccessVerifier", _Verifier)

    legacy = str(tmp_path / "collection.sqlite")
    _monolith(legacy)
    reg = registry.open_registry()
    upgrade.migrate_legacy(reg, "ryan", legacy)
    registry.add_identity(reg, "ryan", _Identity.email)
    reg.close()

    captured = {}

    class _Listener:
        def run(self):
            pass

    def fake_listener(app, port, tls_paths=None, host="0.0.0.0"):
        captured["app"] = app
        return _Listener()

    monkeypatch.setattr(cps, "_new_listener", fake_listener)
    monkeypatch.setattr(cps, "_shared_db_path", None)
    monkeypatch.setattr(cps, "_ingest_executor", None)

    cps.run(argparse.Namespace(db=legacy, port=8081, https=False))

    client = TestClient(captured["app"])
    assert client.get("/health").status_code == 200
    r = client.get("/api/collection", headers={access.HEADER: "tok"})
    assert r.status_code == 200, r.text
    assert r.json()["total_qty"] == 3
