"""Pocket ID client_credentials bearer tokens: /health only, allow-listed clients only."""

import time

import jwt
import pytest
from starlette.testclient import TestClient

from mtg_collector import oidc
from mtg_collector.asgi_app import create_app
from tests.fake_oidc import KID, FakeProvider
from tests.test_isolation_gate import STATIC
from tests.test_oidc_signin import env_for

BOT = "magic-cdn-check"


@pytest.fixture
def provider():
    with FakeProvider() as p:
        yield p


def token(provider, client=BOT, **over):
    now = int(time.time())
    claims = {"iss": provider.issuer, "aud": client, "sub": client, "client_id": client,
              "iat": now, "exp": now + 300, **over}
    return jwt.encode(claims, provider.key, algorithm="RS256", headers={"kid": KID})


def make(provider, tmp_path, *, flag="1", peer="203.0.113.9"):
    env = env_for(provider, MTGC_MACHINE_CLIENTS=BOT, MTGC_HEALTH_REQUIRE_AUTH=flag)
    handler = oidc.Oidc(oidc.load_config(env))
    app = create_app(None, STATIC, str(tmp_path / "c.sqlite"), oidc=handler)
    return TestClient(app, base_url="https://magic.test", follow_redirects=False,
                      client=(peer, 50000))


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_health_without_credentials_is_401(provider, tmp_path):
    assert make(provider, tmp_path).get("/health").status_code == 401


def test_health_stays_open_while_the_flag_is_off(provider, tmp_path):
    assert make(provider, tmp_path, flag="0").get("/health").status_code == 200


def test_allow_listed_client_reaches_health(provider, tmp_path):
    r = make(provider, tmp_path).get("/health", headers=bearer(token(provider)))
    assert r.status_code == 200


def test_client_not_on_the_list_is_refused(provider, tmp_path):
    t = token(provider, client="someone-else")
    assert make(provider, tmp_path).get("/health", headers=bearer(t)).status_code == 401


@pytest.mark.parametrize("over", [{"exp": 1}, {"iss": "https://evil.example"}, {"aud": "other"}])
def test_a_token_failing_verification_is_refused(provider, tmp_path, over):
    t = token(provider, **over)
    assert make(provider, tmp_path).get("/health", headers=bearer(t)).status_code == 401


def test_a_token_signed_by_another_key_is_refused(provider, tmp_path):
    other = FakeProvider()
    t = token(other)
    assert make(provider, tmp_path).get("/health", headers=bearer(t)).status_code == 401


def test_loopback_without_credentials_is_admitted(provider, tmp_path):
    assert make(provider, tmp_path, peer="127.0.0.1").get("/health").status_code == 200


def test_a_proxied_loopback_request_is_not_host_local(provider, tmp_path):
    r = make(provider, tmp_path, peer="127.0.0.1").get(
        "/health", headers={"Cf-Connecting-Ip": "198.51.100.4"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/collection", "/api/collection", "/decks"])
def test_a_machine_token_on_a_tenant_route_is_401(provider, tmp_path, path):
    r = make(provider, tmp_path).get(path, headers=bearer(token(provider)))
    assert r.status_code == 401
