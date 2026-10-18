"""Native Pocket ID sign-in: sign in, group gate, sign out, automation paths."""

import urllib.parse

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mtg_collector import oidc
from mtg_collector.asgi_app import create_app
from tests.fake_oidc import CLIENT_ID, FakeProvider
from tests.test_isolation_gate import STATIC

GROUP = "magic-users"
REDIRECT = "https://magic.test/auth/callback"
BOT = "t" * 40


@pytest.fixture
def provider():
    with FakeProvider() as p:
        yield p


def env_for(provider, **extra):
    return {
        "MTGC_OIDC_ISSUER": provider.issuer,
        "MTGC_OIDC_CLIENT_ID": CLIENT_ID,
        "MTGC_OIDC_CLIENT_SECRET": "s3cret",
        "MTGC_OIDC_REDIRECT_URL": REDIRECT,
        "MTGC_OIDC_REQUIRED_GROUP": GROUP,
        "MTGC_OIDC_COOKIE_KEY": "ab" * 32,
        "MTGC_AUTOMATION_TOKEN": BOT,
        **extra,
    }


@pytest.fixture
def site(provider):
    async def page(request):
        return PlainTextResponse("main page")

    inner = Starlette(routes=[Route("/{path:path}", page, methods=["GET", "POST"])])
    handler = oidc.Oidc(oidc.load_config(env_for(provider)))
    app = oidc.OidcMiddleware(inner, handler)
    return TestClient(app, base_url="https://magic.test", follow_redirects=False)


def sign_in(client, provider, groups, code="c1"):
    login = client.get("/auth/login?return_to=/collection")
    assert login.status_code == 303
    query = urllib.parse.parse_qs(urllib.parse.urlparse(login.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["openid email profile groups"]
    provider.grant(code, sub="u1", email="Me@Example.org", name="Me", groups=groups,
                   nonce=query["nonce"][0])
    return client.get("/auth/callback", params={"code": code, "state": query["state"][0]})


def test_signs_in_and_reaches_the_main_page(site, provider):
    assert site.get("/collection").headers["location"].startswith("/auth/login?return_to=")
    done = sign_in(site, provider, [GROUP])
    assert done.status_code == 303 and done.headers["location"] == "/collection"
    page = site.get("/collection")
    assert (page.status_code, page.text) == (200, "main page")


def test_a_user_outside_the_group_gets_403(site, provider):
    done = sign_in(site, provider, ["someone-else"])
    assert done.status_code == 403
    assert site.get("/collection").status_code == 303  # no session was minted


def test_sign_out_ends_the_session(site, provider):
    sign_in(site, provider, [GROUP])
    assert site.get("/").status_code == 200
    site.get("/auth/logout")
    assert site.get("/").status_code == 303


def test_a_forged_session_cookie_is_refused(site):
    site.cookies.set(oidc.SESSION_COOKIE, "e30.AAAA")
    assert site.get("/").status_code == 303


def test_nonce_mismatch_is_refused(site, provider):
    site.get("/auth/login")
    provider.grant("c2", sub="u1", groups=[GROUP], nonce="not-the-nonce")
    state = oidc.Signer(bytes.fromhex("ab" * 32)).open(
        oidc.FLOW_COOKIE, site.cookies.get(oidc.FLOW_COOKIE, path="/auth"))["state"]
    done = site.get("/auth/callback", params={"code": "c2", "state": state})
    assert done.status_code == 401


def test_open_redirect_is_not_followed(site, provider):
    for bad in ("//evil.example", "https://evil.example", "/\\evil"):
        assert oidc.safe_return_to(bad) == "/"


def test_automation_bearer_and_probes_pass_without_a_session(site):
    assert site.get("/health").status_code == 200
    assert site.get("/api/backup-status").status_code == 200
    ok = site.get("/", headers={"Authorization": f"Bearer {BOT}"})
    assert (ok.status_code, ok.text) == (200, "main page")
    assert site.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 303
    assert site.post("/api/x").status_code == 401


def test_partial_configuration_is_fatal(provider):
    env = env_for(provider)
    del env["MTGC_OIDC_CLIENT_SECRET"]
    with pytest.raises(oidc.OidcConfigError, match="MTGC_OIDC_CLIENT_SECRET"):
        oidc.load_config(env)
    assert oidc.load_config({}) is None


def test_create_app_puts_sign_in_in_front_of_the_legacy_adapter(provider, tmp_path):
    handler = oidc.Oidc(oidc.load_config(env_for(provider)))
    app = create_app(None, STATIC, str(tmp_path / "c.sqlite"), oidc=handler)
    client = TestClient(app, base_url="https://magic.test", follow_redirects=False)
    assert client.get("/collection").status_code == 303
    assert client.get("/health").status_code == 200
