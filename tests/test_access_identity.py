"""Access JWT verification, tenant resolution, and multi-mode front door (sp-qwlb0o).

Tier 1: no container, no network. A throwaway RSA key signs the tokens and the
JWKS is served by a fake fetch.
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from mtg_collector import access
from mtg_collector.asgi_app import PUBLIC_ROUTES, create_app
from mtg_collector.cli import crack_pack_server as cps
from mtg_collector.db import registry
from mtg_collector.tenancy import MultiTenantResolver, current_tenant

ISS = "https://team.cloudflareaccess.com"
AUD = "aud-tag"
ENV = {
    access.ENV_TEAM_DOMAIN: ISS,
    access.ENV_AUD: AUD,
    access.ENV_JWKS_URL: "http://jwks.invalid/certs",
}


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY = _key()
OTHER = _key()


def _jwk(key, kid):
    d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    d.update(kid=kid, alg="RS256", use="sig")
    return d


def _token(email="a@x.org", key=KEY, kid="k1", **over):
    now = int(time.time())
    claims = {"iss": ISS, "aud": [AUD], "iat": now, "exp": now + 600}
    if email is not None:
        claims["email"] = email
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def _verifier(keys=None, clock=None, fetches=None):
    keys = keys if keys is not None else [_jwk(KEY, "k1")]

    def fetch(url):
        if fetches is not None:
            fetches.append(url)
        return {"keys": keys}

    return access.AccessVerifier(access.load_config(ENV), fetch=fetch,
                                 clock=clock or Clock())


# --- config ---------------------------------------------------------------

def test_no_config_is_none():
    assert access.load_config({}) is None


def test_all_three_is_config():
    assert access.load_config(ENV).aud == AUD


@pytest.mark.parametrize("drop", list(ENV))
def test_partial_config_is_fatal(drop):
    env = {k: v for k, v in ENV.items() if k != drop}
    with pytest.raises(access.AccessConfigError, match=drop):
        access.load_config(env)


def test_multi_without_access_refuses():
    with pytest.raises(access.AccessConfigError):
        access.require_config({})


def test_multi_mode_switch_is_opt_in():
    assert not access.multitenant_enabled({})
    assert not access.multitenant_enabled({"MTGC_MULTITENANT": ""})
    assert access.multitenant_enabled({"MTGC_MULTITENANT": "1"})


# --- JWT negative list ----------------------------------------------------

def test_good_token_names_the_email():
    assert _verifier().verify(_token()).email == "a@x.org"


def test_header_beats_cookie():
    assert access.token_from({access.HEADER: "H"}, "CF_Authorization=C") == "H"
    assert access.token_from({}, "x=1; CF_Authorization=C") == "C"
    assert access.token_from({}, None) is None


@pytest.mark.parametrize("make", [
    lambda: _token(exp=int(time.time()) - 10),
    lambda: _token(aud=["other"]),
    lambda: _token(iss="https://evil.example"),
    lambda: _token(key=OTHER),
    lambda: _token(kid="unknown"),
    lambda: _token(email=None),
    lambda: "not.a.jwt",
    lambda: jwt.encode({"iss": ISS, "aud": AUD, "iat": 1, "exp": 2**31, "email": "a@x.org"},
                       "secret", algorithm="HS256", headers={"kid": "k1"}),
    lambda: jwt.encode({"iss": ISS, "aud": AUD, "iat": 1, "exp": 2**31, "email": "a@x.org"},
                       None, algorithm="none", headers={"kid": "k1"}),
])
def test_negative_list(make):
    with pytest.raises(access.AccessDenied):
        _verifier().verify(make())


def test_jwks_cached_and_kid_miss_refresh_rate_limited():
    fetches, clock = [], Clock()
    v = _verifier(fetches=fetches, clock=clock)
    v.verify(_token())
    v.verify(_token())
    assert len(fetches) == 1
    with pytest.raises(access.AccessDenied):
        v.verify(_token(kid="new"))
    assert len(fetches) == 1  # inside 60 s: no refresh
    clock.t += 61
    with pytest.raises(access.AccessDenied):
        v.verify(_token(kid="new"))
    assert len(fetches) == 2
    clock.t += 3601
    v.verify(_token())
    assert len(fetches) == 3


# --- front door in multi mode ---------------------------------------------

@pytest.fixture
def multi(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    reg = registry.open_registry()
    dbid = registry.create_tenant(reg, "alice")
    registry.add_identity(reg, "alice", "a@x.org")
    reg.close()
    static = tmp_path / "static"
    static.mkdir()
    (static / "home.html").write_text("<html>home</html>")
    app = create_app(None, static, str(tmp_path / "legacy.sqlite"),
                     resolver=MultiTenantResolver(_verifier()), multi=True)
    return TestClient(app), dbid, tmp_path


def _hdr(token):
    return {access.HEADER: token}


def test_no_token_is_401(multi):
    c, _, _ = multi
    assert c.get("/api/sets").status_code == 401


def test_bad_token_is_401(multi):
    c, _, _ = multi
    assert c.get("/api/sets", headers=_hdr(_token(key=OTHER))).status_code == 401


def test_unbound_email_is_403_naming_the_fix(multi):
    c, _, _ = multi
    r = c.get("/api/sets", headers=_hdr(_token("nobody@x.org")))
    assert r.status_code == 403
    assert "mtg tenant identity add" in r.json()["error"]


def test_lookup_provisions_nothing(multi):
    c, _, home = multi
    before = sorted(p.name for p in (home / "tenants").iterdir())
    c.get("/api/sets", headers=_hdr(_token("nobody@x.org")))
    assert sorted(p.name for p in (home / "tenants").iterdir()) == before


def test_bound_email_binds_its_database_id(multi, monkeypatch):
    c, dbid, _ = multi
    seen = []

    def spy(self):
        seen.append(current_tenant().value)
        self._send_json({"ok": True})

    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets", spy)
    r = c.get("/api/sets", headers=_hdr(_token()))
    assert r.status_code == 200 and seen == [dbid]


def test_cookie_identity_works(multi, monkeypatch):
    c, dbid, _ = multi
    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets",
                        lambda self: self._send_json({"ok": True}))
    c.cookies.set("CF_Authorization", _token())
    assert c.get("/api/sets").status_code == 200


def test_get_conn_opens_the_tenants_file(multi, monkeypatch):
    c, dbid, home = multi
    seen = []

    def spy(self):
        seen.append(self.db_path)
        opened = []
        monkeypatch.setattr("mtg_collector.tenancy.connection.open_connection",
                            lambda path, shared, **kw: opened.append(path) or object())
        self._get_conn()
        self._send_json({"path": opened[0]})

    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets", spy)
    r = c.get("/api/sets", headers=_hdr(_token()))
    assert r.json()["path"] == str(home / "tenants" / f"{dbid}.sqlite")


def test_public_routes_are_a_pinned_list():
    assert PUBLIC_ROUTES == ("/health", "/api/backup-status")


def test_health_is_public_and_binds_no_tenant(multi):
    c, _, _ = multi
    r = c.get("/health")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, no-store"


def test_tenant_responses_are_private_no_store(multi, monkeypatch):
    c, _, _ = multi
    monkeypatch.setattr(cps.CrackPackHandler, "_api_sets",
                        lambda self: self._send_json({"ok": True}))
    r = c.get("/api/sets", headers=_hdr(_token()))
    assert r.headers["cache-control"] == "private, no-store"
    assert r.status_code == 200


def test_refusals_are_not_cacheable(multi):
    c, _, _ = multi
    assert c.get("/collection").headers["cache-control"] == "private, no-store"
