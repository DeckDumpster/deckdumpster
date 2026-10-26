"""Multi-tenant mode accepts a Pocket ID session beside an Access JWT (sp-22lukk)."""

import pytest
from starlette.testclient import TestClient

from mtg_collector import access, oidc
from mtg_collector.asgi_app import create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db import registry
from mtg_collector.tenancy import MultiTenantResolver, current_tenant
from tests.fake_oidc import FakeProvider
from tests.test_access_identity import _token, _verifier
from tests.test_oidc_signin import GROUP, env_for, sign_in


@pytest.fixture
def provider():
    with FakeProvider() as p:
        yield p


@pytest.fixture
def multi(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    reg = registry.open_registry()
    ids = {}
    for handle, email in (("alice", "me@example.org"), ("bobby", "b@x.org")):
        ids[handle] = registry.create_tenant(reg, handle)
        registry.add_identity(reg, handle, email)
    reg.close()
    static = tmp_path / "static"
    static.mkdir()
    handler = oidc.Oidc(oidc.load_config(env_for(provider)))
    app = create_app(None, static, str(tmp_path / "legacy.sqlite"),
                     resolver=MultiTenantResolver(_verifier(), oidc=handler),
                     multi=True, oidc=handler)
    seen = []

    def spy(self):
        seen.append(current_tenant().value)
        self._send_json({"ok": True})

    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets", spy)
    client = TestClient(app, base_url="https://magic.test", follow_redirects=False)
    return client, ids, seen


def test_multi_app_with_oidc_starts(multi):
    client, _, _ = multi
    assert client.get("/health").status_code == 200


def test_session_sees_its_own_tenant_only(multi, provider):
    client, ids, seen = multi
    assert sign_in(client, provider, [GROUP]).status_code == 303
    assert client.get("/api/sets").status_code == 200
    assert seen == [ids["alice"]]
    assert ids["bobby"] not in seen


def test_session_outside_the_group_is_refused(multi, provider):
    client, _, seen = multi
    assert sign_in(client, provider, ["other"]).status_code == 403
    assert client.get("/api/sets").status_code in (303, 401, 403)
    assert seen == []


def test_session_for_an_unbound_email_is_403(multi, provider, tmp_path):
    client, _, seen = multi
    reg = registry.open_registry()
    registry.remove_identity(reg, "me@example.org")
    reg.close()
    sign_in(client, provider, [GROUP])
    assert client.get("/api/sets").status_code == 403
    assert seen == []


def test_access_jwt_still_resolves_beside_oidc(multi):
    client, ids, seen = multi
    r = client.get("/api/sets", headers={access.HEADER: _token("b@x.org")})
    assert r.status_code == 200 and seen == [ids["bobby"]]


def test_neither_is_refused(multi):
    client, _, seen = multi
    assert client.get("/api/sets", headers={"Sec-Fetch-Mode": "cors"}).status_code == 401
    assert client.get("/api/sets", headers={access.HEADER: "junk",
                                            "Sec-Fetch-Mode": "cors"}).status_code == 401
    assert seen == []
