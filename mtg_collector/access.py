"""Cloudflare Access identity: verify the JWT, name the person (multi-tenancy D10).

``verify`` turns a request's ``Cf-Access-Jwt-Assertion`` header (or, failing
that, its ``CF_Authorization`` cookie) into a ``VerifiedIdentity`` or raises
``AccessDenied``. Nothing here reads a registry or creates anything.

Configuration is three environment variables, all or none. Multi-tenant mode
needs all three; one or two set is a fatal misconfiguration in *either* mode,
because a half-armed gate reads as an armed one.

    MTGC_ACCESS_TEAM_DOMAIN  https://<team>.cloudflareaccess.com (the issuer)
    MTGC_ACCESS_AUD          the Access application's audience tag
    MTGC_ACCESS_JWKS_URL     where the signing keys are published

Only RS256 is accepted: the algorithm comes from this module, never from the
token's own header, so ``alg: none`` and HS256-with-the-public-key confusion
have nothing to land on.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass

import jwt

ENV_TEAM_DOMAIN = "MTGC_ACCESS_TEAM_DOMAIN"
ENV_AUD = "MTGC_ACCESS_AUD"
ENV_JWKS_URL = "MTGC_ACCESS_JWKS_URL"
ENV_MULTITENANT = "MTGC_MULTITENANT"
_ENV_ALL = (ENV_TEAM_DOMAIN, ENV_AUD, ENV_JWKS_URL)

HEADER = "cf-access-jwt-assertion"
COOKIE = "CF_Authorization"

JWKS_TTL_S = 3600
JWKS_MISS_REFRESH_MIN_S = 60
ALGORITHMS = ["RS256"]


class AccessConfigError(RuntimeError):
    """The Access configuration is partial or missing where it is required."""


class AccessDenied(Exception):
    """The request carries no acceptable identity: a 401."""


@dataclass(frozen=True)
class VerifiedIdentity:
    email: str


@dataclass(frozen=True)
class AccessConfig:
    team_domain: str
    aud: str
    jwks_url: str


def multitenant_enabled(environ=None) -> bool:
    raw = (environ if environ is not None else os.environ).get(ENV_MULTITENANT, "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_config(environ=None) -> AccessConfig | None:
    """The configured Access gate, None when unconfigured, fatal when partial."""
    env = environ if environ is not None else os.environ
    values = {k: env.get(k, "").strip() for k in _ENV_ALL}
    present = [k for k, v in values.items() if v]
    if not present:
        return None
    if len(present) != len(_ENV_ALL):
        missing = [k for k in _ENV_ALL if not values[k]]
        raise AccessConfigError(
            "partial Access configuration: set all of "
            f"{', '.join(_ENV_ALL)} or none; missing {', '.join(missing)}"
        )
    return AccessConfig(
        team_domain=values[ENV_TEAM_DOMAIN].rstrip("/"),
        aud=values[ENV_AUD],
        jwks_url=values[ENV_JWKS_URL],
    )


def require_config(environ=None) -> AccessConfig:
    """Multi-tenant mode refuses to start without the gate."""
    cfg = load_config(environ)
    if cfg is None:
        raise AccessConfigError(
            f"{ENV_MULTITENANT} is set but Access is not configured: "
            f"set {', '.join(_ENV_ALL)} (see ~/.config/mtgc/<instance>/access.env)"
        )
    return cfg


def _fetch_jwks(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.load(resp)


class AccessVerifier:
    def __init__(self, config: AccessConfig, *, fetch=_fetch_jwks, clock=time.monotonic):
        self._config = config
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, object] = {}
        self._fetched_at: float | None = None

    def _refresh(self) -> None:
        jwks = self._fetch(self._config.jwks_url)
        keys = {}
        for jwk in jwks.get("keys", []):
            if jwk.get("kty") == "RSA" and jwk.get("kid"):
                keys[jwk["kid"]] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        self._keys = keys
        self._fetched_at = self._clock()

    def _key_for(self, kid: str):
        with self._lock:
            now = self._clock()
            if self._fetched_at is None or now - self._fetched_at >= JWKS_TTL_S:
                self._refresh()
            elif kid not in self._keys and now - self._fetched_at >= JWKS_MISS_REFRESH_MIN_S:
                self._refresh()
            return self._keys.get(kid)

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AccessDenied(f"malformed token: {exc}") from exc
        if header.get("alg") not in ALGORITHMS:
            raise AccessDenied(f"algorithm {header.get('alg')!r} is not accepted")
        kid = header.get("kid")
        if not kid:
            raise AccessDenied("token names no signing key")
        key = self._key_for(kid)
        if key is None:
            raise AccessDenied("token signed by an unknown key")
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._config.aud,
                issuer=self._config.team_domain,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise AccessDenied(f"token rejected: {exc}") from exc
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            # A service-token JWT carries no email: it names no person.
            raise AccessDenied("token carries no email")
        return VerifiedIdentity(email=email.strip())


def token_from(headers, cookie_header: str | None) -> str | None:
    """The header wins over the cookie when both are present."""
    value = headers.get(HEADER)
    if value:
        return value.strip()
    if cookie_header:
        for part in cookie_header.split(";"):
            name, _, val = part.strip().partition("=")
            if name == COOKIE and val:
                return val
    return None
