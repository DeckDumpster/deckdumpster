"""Which tenant a request belongs to, and the only way to ask.

A ``TenantId`` can be minted by this module and nowhere else: the constructor
demands a token only the resolvers here hold, so a handler cannot conjure a
tenant out of a string it read from a header. The id travels in a contextvar set
by the front door's middleware, and ``current_tenant()`` *raises* outside a
request -- there is no database outside a resolved request.

Single-tenant mode, the default, is the same path with a resolver that always
returns the one configured tenant.
"""

from __future__ import annotations

import contextlib
import contextvars

_MINT = object()


class NoTenantError(RuntimeError):
    """A tenant-scoped resource was asked for outside a resolved request."""


class TenantId:
    __slots__ = ("_value",)

    def __init__(self, value: str, *, _mint: object = None):
        if _mint is not _MINT:
            raise TypeError("TenantId is minted by a tenant resolver, never constructed")
        if not value:
            raise ValueError("a tenant id cannot be empty")
        object.__setattr__(self, "_value", value)

    def __setattr__(self, name, value):
        raise AttributeError("TenantId is immutable")

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other):
        return isinstance(other, TenantId) and other._value == self._value

    def __hash__(self):
        return hash(self._value)

    def __repr__(self):
        return f"TenantId({self._value!r})"


SINGLE_TENANT = "single"

_current: contextvars.ContextVar[TenantId | None] = contextvars.ContextVar(
    "mtgc_tenant", default=None
)


class SingleTenantResolver:
    """Resolves every request to the one configured tenant."""

    def __init__(self, value: str = SINGLE_TENANT):
        self._tenant = TenantId(value, _mint=_MINT)

    def resolve(self, scope) -> TenantId:
        return self._tenant


class Forbidden(Exception):
    """A verified identity that no tenant claims: a 403 that names the fix."""


class MultiTenantResolver:
    """Verified identity -> registry -> TenantId. Never creates anything.

    The id it mints is the tenant's opaque database_id, the only thing a path is
    ever built from.
    """

    def __init__(self, verifier, registry_path=None, oidc=None):
        self._verifier = verifier
        self._registry_path = registry_path
        self._oidc = oidc

    @staticmethod
    def _access_token(scope):
        from mtg_collector import access

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope["headers"]}
        return access.token_from(headers, headers.get("cookie"))

    def carries_valid_access(self, scope) -> bool:
        """True when the request's Access JWT verifies: lets it past the sign-in layer."""
        from mtg_collector import access

        token = self._access_token(scope)
        if token is None:
            return False
        try:
            self._verifier.verify(token)
        except access.AccessDenied:
            return False
        return True

    def _oidc_email(self, scope):
        """The verified email of a signed-in session in the required group, else None."""
        if self._oidc is None:
            return None
        from starlette.requests import Request

        user = self._oidc.session(Request(scope))
        if user is None or self._oidc.cfg.required_group not in user["groups"]:
            return None
        return user["email"] or None

    def resolve(self, scope) -> TenantId:
        from mtg_collector import access
        from mtg_collector.db import registry

        email = self._oidc_email(scope)
        if email is None:
            token = self._access_token(scope)
            if token is None:
                raise access.AccessDenied("no Access token or sign-in session")
            email = self._verifier.verify(token).email
        identity = access.VerifiedIdentity(email=email)
        conn = registry.open_registry(self._registry_path, create=False)
        try:
            database_id = registry.resolve_identity(conn, identity.email)
        finally:
            conn.close()
        if database_id is None:
            raise Forbidden(
                f"{identity.email} is not bound to a tenant: "
                f"ask the operator to run `mtg tenant identity add <handle> {identity.email}`"
            )
        return TenantId(database_id, _mint=_MINT)


def current_tenant() -> TenantId:
    tenant = _current.get()
    if tenant is None:
        raise NoTenantError("no tenant is bound: this runs only inside a resolved request")
    return tenant


@contextlib.contextmanager
def bind(tenant: TenantId):
    token = _current.set(tenant)
    try:
        yield tenant
    finally:
        _current.reset(token)
