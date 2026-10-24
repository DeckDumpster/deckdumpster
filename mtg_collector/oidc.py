"""Native OIDC sign-in against Pocket ID (the Python counterpart of dumpster-kit-oidc).

The app signs users in itself -- authorization-code flow with PKCE, ``state`` and
``nonce`` -- instead of sitting behind Cloudflare Access's login page. The contract is
the kit's: ``/auth/login``, ``/auth/callback``, ``/auth/logout``; scopes
``openid email profile groups``; the ID token is verified RS256 against the provider's
JWKS (``iss``, ``aud``, ``exp``, ``iat``, ``nonce``); the ``groups`` claim must contain
``REQUIRED_GROUP`` or the user gets a 403 and no session; the session is a signed
``HttpOnly; Secure; SameSite=Lax`` cookie and the group rule is applied again on every
request.

Configuration is the environment, all of it required (one half-set is a startup error):

    MTGC_OIDC_ISSUER          https://id.gantt.pub
    MTGC_OIDC_CLIENT_ID / MTGC_OIDC_CLIENT_SECRET
    MTGC_OIDC_REDIRECT_URL    absolute URL of /auth/callback on this site
    MTGC_OIDC_REQUIRED_GROUP  magic-users
    MTGC_OIDC_COOKIE_KEY      >= 32 bytes, hex or base64
    MTGC_OIDC_SESSION_TTL_SECS  optional, default 8 hours

Automation (the deploy job's cdn-check, probes) does not sign in: it presents
``Authorization: Bearer $MTGC_AUTOMATION_TOKEN``. ``PUBLIC_PATHS`` are ops probes served
with no credential at all.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass

import jwt
import requests
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

ENV_PREFIX = "MTGC_OIDC_"
ENV_AUTOMATION_TOKEN = "MTGC_AUTOMATION_TOKEN"
_REQUIRED = ("ISSUER", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URL", "REQUIRED_GROUP",
             "COOKIE_KEY")

SESSION_COOKIE = "dk_session"
FLOW_COOKIE = "dk_oidc_flow"
FLOW_TTL_S = 600
DEFAULT_SESSION_TTL_S = 8 * 3600
SCOPES = "openid email profile groups"
CLOCK_SKEW_S = 60
JWKS_REFETCH_MIN_S = 60
ALGORITHMS = ["RS256"]

# Ops probes (serving-check, backup-check, cdn-check's /health): no credential.
PUBLIC_PATHS = ("/health", "/api/backup-status")

# Marks a 401 as "sign in again", which static/session-guard.js turns into the login redirect.
LOGIN_REQUIRED_HEADER = "X-Login-Required"


class OidcConfigError(RuntimeError):
    """The OIDC configuration is partial, malformed, or incompatible with the mode."""


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_url: str
    required_group: str
    cookie_key: bytes
    session_ttl_s: int
    automation_token: str | None


def _decode_key(raw: str) -> bytes | None:
    if len(raw) % 2 == 0:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    for decode in (base64.b64decode, lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))):
        try:
            return decode(raw)
        except (binascii.Error, ValueError):
            continue
    return None


def load_config(environ=None) -> OidcConfig | None:
    """The configured sign-in, None when unconfigured, fatal when partial."""
    env = environ if environ is not None else os.environ
    values = {k: env.get(ENV_PREFIX + k, "").strip() for k in _REQUIRED}
    if not any(values.values()):
        return None
    missing = [ENV_PREFIX + k for k in _REQUIRED if not values[k]]
    if missing:
        raise OidcConfigError(f"missing environment: {', '.join(missing)}")
    key = _decode_key(values["COOKIE_KEY"])
    if key is None or len(key) < 32:
        raise OidcConfigError(f"{ENV_PREFIX}COOKIE_KEY must be hex or base64 of at least 32 bytes")
    ttl_raw = env.get(ENV_PREFIX + "SESSION_TTL_SECS", "").strip()
    try:
        ttl = int(ttl_raw) if ttl_raw else DEFAULT_SESSION_TTL_S
    except ValueError:
        raise OidcConfigError(f"{ENV_PREFIX}SESSION_TTL_SECS must be whole seconds") from None
    token = env.get(ENV_AUTOMATION_TOKEN, "").strip() or None
    if token is not None and len(token) < 32:
        raise OidcConfigError(f"{ENV_AUTOMATION_TOKEN} must be at least 32 characters")
    return OidcConfig(
        issuer=values["ISSUER"].rstrip("/"),
        client_id=values["CLIENT_ID"],
        client_secret=values["CLIENT_SECRET"],
        redirect_url=values["REDIRECT_URL"],
        required_group=values["REQUIRED_GROUP"],
        cookie_key=key,
        session_ttl_s=ttl,
        automation_token=token,
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _random(n: int) -> str:
    return _b64(secrets.token_bytes(n))


class Signer:
    """HMAC-signed cookie values, domain-separated by cookie name."""

    def __init__(self, key: bytes):
        self._key = key

    def _mac(self, name: str, body: str) -> str:
        return _b64(hmac.new(self._key, f"{name}.{body}".encode(), hashlib.sha256).digest())

    def seal(self, name: str, payload: dict) -> str:
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        return f"{body}.{self._mac(name, body)}"

    def open(self, name: str, value: str) -> dict | None:
        body, _, mac = value.partition(".")
        if not body or not hmac.compare_digest(mac, self._mac(name, body)):
            return None
        try:
            return json.loads(_unb64(body))
        except ValueError:
            return None


def safe_return_to(value: str) -> str:
    """Only a path on this site: a leading /, no //, no backslash, no control characters."""
    ok = (value.startswith("/") and not value.startswith("//") and "\\" not in value
          and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    return value if ok else "/"


def _cookie_header(name: str, value: str, path: str, max_age: int) -> str:
    return f"{name}={value}; Path={path}; HttpOnly; Secure; SameSite=Lax; Max-Age={max_age}"


FORBIDDEN_HTML = (
    "<!doctype html><title>Access denied</title><h1>Access denied</h1>"
    "<p>You are signed in, but your account is not a member of the group this site "
    'requires. Ask the owner to add you, then <a href="/auth/logout">sign out</a> '
    "and back in.</p>"
)


def _refusal(status: int, message: str) -> Response:
    return JSONResponse({"error": message}, status_code=status)


class Oidc:
    def __init__(self, config: OidcConfig, *, http=None, clock=time.time):
        self.cfg = config
        self._http = http or requests.Session()
        self._clock = clock
        self._signer = Signer(config.cookie_key)
        self._keys: dict[str, object] = {}
        self._keys_fetched_at: float | None = None
        url = f"{config.issuer}/.well-known/openid-configuration"
        disc = self._get_json(url)
        if disc["issuer"].rstrip("/") != config.issuer:
            raise OidcConfigError(
                f"discovery issuer {disc['issuer']} does not match configured {config.issuer}")
        self._authorization_endpoint = disc["authorization_endpoint"]
        self._token_endpoint = disc["token_endpoint"]
        self._jwks_uri = disc["jwks_uri"]
        self._refresh_keys()

    # -- provider -----------------------------------------------------------------
    def _get_json(self, url: str) -> dict:
        resp = self._http.get(url, timeout=10, allow_redirects=False)
        resp.raise_for_status()
        return resp.json()

    def _refresh_keys(self) -> None:
        keys = {}
        for jwk in self._get_json(self._jwks_uri).get("keys", []):
            if jwk.get("kty") == "RSA" and jwk.get("kid"):
                keys[jwk["kid"]] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        self._keys = keys
        self._keys_fetched_at = self._clock()

    def _key_for(self, kid: str):
        if kid not in self._keys and self._clock() - self._keys_fetched_at >= JWKS_REFETCH_MIN_S:
            self._refresh_keys()
        return self._keys.get(kid)

    def _verify_id_token(self, token: str, nonce: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise PermissionError("invalid id_token") from None
        if header.get("alg") not in ALGORITHMS or not header.get("kid"):
            raise PermissionError("invalid id_token")
        key = self._key_for(header["kid"])
        if key is None:
            raise PermissionError("id_token signed by unknown key")
        try:
            claims = jwt.decode(
                token, key, algorithms=ALGORITHMS, audience=self.cfg.client_id,
                issuer=self.cfg.issuer, options={"require": ["exp", "iat", "iss", "aud"],
                                                 "verify_exp": False, "verify_iat": False})
        except jwt.PyJWTError:
            raise PermissionError("id_token rejected") from None
        now = self._clock()
        if (claims["exp"] + CLOCK_SKEW_S <= now or claims["iat"] > now + CLOCK_SKEW_S):
            raise PermissionError("id_token outside its validity")
        if claims.get("nonce") != nonce:
            raise PermissionError("nonce mismatch")
        if not claims.get("sub"):
            raise PermissionError("id_token has no subject")
        return claims

    # -- session ------------------------------------------------------------------
    def session(self, request: Request) -> dict | None:
        raw = request.cookies.get(SESSION_COOKIE)
        user = self._signer.open(SESSION_COOKIE, raw) if raw else None
        if user is None or user.get("exp", 0) <= self._clock():
            return None
        return user

    def automation_ok(self, request: Request) -> bool:
        expected = self.cfg.automation_token
        auth = request.headers.get("authorization", "")
        scheme, _, presented = auth.partition(" ")
        return (expected is not None and scheme.lower() == "bearer"
                and hmac.compare_digest(presented.strip().encode(), expected.encode()))

    # -- routes -------------------------------------------------------------------
    def login(self, request: Request) -> Response:
        verifier = _random(48)
        flow = {
            "state": _random(24), "nonce": _random(24), "verifier": verifier,
            "return_to": safe_return_to(request.query_params.get("return_to", "/")),
            "exp": int(self._clock()) + FLOW_TTL_S,
        }
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        query = urllib.parse.urlencode({
            "response_type": "code", "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_url, "scope": SCOPES,
            "state": flow["state"], "nonce": flow["nonce"],
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        sep = "&" if "?" in self._authorization_endpoint else "?"
        resp = RedirectResponse(f"{self._authorization_endpoint}{sep}{query}", status_code=303)
        resp.headers.append("set-cookie", _cookie_header(
            FLOW_COOKIE, self._signer.seal(FLOW_COOKIE, flow), "/auth", FLOW_TTL_S))
        return resp

    def callback(self, request: Request) -> Response:
        raw = request.cookies.get(FLOW_COOKIE)
        flow = self._signer.open(FLOW_COOKIE, raw) if raw else None
        if flow is None or flow.get("exp", 0) <= self._clock():
            return _refusal(400, "sign-in expired or not started; try again")
        q = request.query_params
        if q.get("state") != flow["state"]:
            return _refusal(400, "state mismatch")
        if "error" in q:
            return _refusal(401, "the provider refused the sign-in")
        code = q.get("code")
        if not code:
            return _refusal(400, "no authorization code")
        try:
            resp = self._http.post(self._token_endpoint, timeout=10, allow_redirects=False, data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": self.cfg.redirect_url, "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret, "code_verifier": flow["verifier"],
            })
        except requests.RequestException:
            return _refusal(502, "provider unreachable")
        if not resp.ok:
            return _refusal(401, "the provider refused the code")
        try:
            claims = self._verify_id_token(resp.json()["id_token"], flow["nonce"])
        except (KeyError, ValueError):
            return _refusal(502, "malformed token response")
        except PermissionError as exc:
            return _refusal(401, str(exc))

        clear_flow = _cookie_header(FLOW_COOKIE, "", "/auth", 0)
        groups = claims.get("groups") or []
        if self.cfg.required_group not in groups:
            denied = HTMLResponse(FORBIDDEN_HTML, status_code=403)
            denied.headers.append("set-cookie", clear_flow)
            return denied
        user = {
            "sub": claims["sub"], "email": (claims.get("email") or "").lower(),
            "name": claims.get("name") or claims.get("preferred_username") or "",
            "groups": groups, "exp": int(self._clock()) + self.cfg.session_ttl_s,
        }
        out = RedirectResponse(safe_return_to(flow["return_to"]), status_code=303)
        out.headers.append("set-cookie", _cookie_header(
            SESSION_COOKIE, self._signer.seal(SESSION_COOKIE, user), "/",
            self.cfg.session_ttl_s))
        out.headers.append("set-cookie", clear_flow)
        return out

    def logout(self, request: Request) -> Response:
        out = RedirectResponse("/", status_code=303)
        out.headers.append("set-cookie", _cookie_header(SESSION_COOKIE, "", "/", 0))
        return out


class OidcMiddleware:
    """Outermost ASGI layer: every human path needs a session in the required group.

    Browser navigations are sent to /auth/login; in-page requests (fetch/XHR) get a 401 the page turns into that redirect. A user
    signed in outside the group gets the 403 page. Public probes and automation
    (bearer token) pass.
    """

    def __init__(self, app, oidc: Oidc):
        self.app = app
        self.oidc = oidc

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        path = scope["path"]
        routes = {"/auth/login": self.oidc.login, "/auth/callback": self.oidc.callback,
                  "/auth/logout": self.oidc.logout}
        if path in routes:
            import asyncio
            response = await asyncio.to_thread(routes[path], request)
            await response(scope, receive, send)
            return
        if path in PUBLIC_PATHS or self.oidc.automation_ok(request):
            await self.app(scope, receive, send)
            return
        user = self.oidc.session(request)
        if user is not None and self.oidc.cfg.required_group in user["groups"]:
            await self.app(scope, receive, send)
            return
        if user is not None:
            response: Response = HTMLResponse(FORBIDDEN_HTML, status_code=403)
        elif self._navigates(scope):
            target = scope["raw_path"].decode("latin-1")
            if scope["query_string"]:
                target += "?" + scope["query_string"].decode("latin-1")
            response = RedirectResponse(
                "/auth/login?" + urllib.parse.urlencode({"return_to": target}), status_code=303)
        else:
            response = JSONResponse({"error": "sign-in required"}, status_code=401,
                                    headers={LOGIN_REQUIRED_HEADER: "1"})
        await response(scope, receive, send)

    @staticmethod
    def _navigates(scope) -> bool:
        """A browser navigation can follow a redirect to the login page; a fetch cannot.

        ``Sec-Fetch-Mode`` is sent by every current browser. Without it (curl, probes)
        a GET is taken as a navigation, as before.
        """
        mode = dict(scope["headers"]).get(b"sec-fetch-mode")
        if mode is not None:
            return mode == b"navigate"
        return scope["method"] == "GET"
