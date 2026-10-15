"""The ASGI front door: the only listener (multi-tenancy N3, a strangler).

Every request passes the tenant middleware, which resolves a ``TenantId`` and
binds it for the duration of the request. A route then either is a native
FastAPI handler or falls through to the legacy adapter, which runs the existing
``CrackPackHandler`` logic unchanged against the request and relays what it
wrote. Routes move to native handlers family by family; the adapter shrinks to
nothing.
"""

from __future__ import annotations

import asyncio
import contextvars
import email.message
import io
import json
import os
import sys
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from mtg_collector.access import AccessDenied
from mtg_collector.cli.crack_pack_server import CrackPackHandler
from mtg_collector.http_cache import CACHE_HASHED_ASSET
from mtg_collector.routes import collection as collection_routes
from mtg_collector.tenancy import Forbidden, SingleTenantResolver, bind

# The only routes served without an identity in multi-tenant mode: ops probes
# (serving-check, backup-check, cdn-check). A ratchet test pins this tuple; a
# route joins it by a reviewed edit here, never by a handler opting out.
PUBLIC_ROUTES = ("/health", "/api/backup-status")

# N4: a tenant response cached at the edge would be served to another tenant.
CACHE_TENANT = "private, no-store"
VARY_TENANT = "Cookie, Cf-Access-Jwt-Assertion, Accept-Encoding"

LEGACY_METHODS = ["GET", "POST", "PUT", "DELETE"]

# The handler writes a raw HTTP/1.1 response; these are the framing headers the
# ASGI server owns and would otherwise duplicate or contradict.
_SERVER_OWNED = {"connection", "keep-alive", "transfer-encoding", "server", "date"}


class TenantMiddleware:
    """Resolve the tenant, bind it, run the request inside the binding.

    ``multi`` is multi-tenant mode: the resolver may refuse (401 bad or absent
    identity, 403 unbound), ``PUBLIC_ROUTES`` skip resolution and bind no tenant,
    and every response but a content-addressed asset is ``private, no-store``.
    """

    def __init__(self, app, resolver, multi: bool = False):
        self.app = app
        self.resolver = resolver
        self.multi = multi

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if not self.multi:
            with bind(self.resolver.resolve(scope)):
                await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            raise RuntimeError("multi-tenant mode serves http only")
        if scope["path"] in PUBLIC_ROUTES:
            await self.app(scope, receive, self._private(send))
            return
        try:
            tenant = await asyncio.to_thread(self.resolver.resolve, scope)
        except AccessDenied as exc:
            await self._refuse(send, 401, str(exc))
            return
        except Forbidden as exc:
            await self._refuse(send, 403, str(exc))
            return
        with bind(tenant):
            await self.app(scope, receive, self._private(send))

    @staticmethod
    def _private(send):
        async def wrapped(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message["headers"]
                           if k.lower() not in (b"cache-control", b"etag", b"vary")]
                original = [v for k, v in message["headers"] if k.lower() == b"cache-control"]
                if original and original[-1].decode("latin-1") == CACHE_HASHED_ASSET:
                    message = {**message, "headers": message["headers"]}
                else:
                    headers.append((b"cache-control", CACHE_TENANT.encode()))
                    # Belt and braces: a cache that stores despite no-store
                    # (an edge rule overriding origin) must still key on identity.
                    headers.append((b"vary", VARY_TENANT.encode()))
                    message = {**message, "headers": headers}
            await send(message)
        return wrapped

    async def _refuse(self, send, status: int, detail: str):
        body = json.dumps({"error": detail}).encode()
        await self._private(send)({
            "type": "http.response.start", "status": status,
            "headers": [(b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


class _Pipe:
    """The handler's wfile: bytes cross from its thread into an asyncio queue."""

    def __init__(self, loop, queue):
        self._loop = loop
        self._queue = queue

    def write(self, data):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, bytes(data))
        return len(data)

    def flush(self):
        pass


class _AdaptedHandler(CrackPackHandler):
    """CrackPackHandler fed from an ASGI request instead of a socket."""

    def __init__(self, generator, static_dir, db_path, *, request, pipe):
        self._adapted = request
        self._pipe = pipe
        super().__init__(generator, static_dir, db_path, None, request["client"], None)

    def setup(self):
        self.rfile = io.BytesIO(self._adapted["body"])
        self.wfile = self._pipe

    def handle(self):
        req = self._adapted
        self.command = req["method"]
        self.path = req["target"]
        self.request_version = "HTTP/1.1"
        self.requestline = f"{self.command} {self.path} HTTP/1.1"
        self.close_connection = True
        self.headers = req["headers"]
        getattr(self, "do_" + self.command)()

    def finish(self):
        pass


def _message_headers(scope, body: bytes) -> email.message.Message:
    msg = email.message.Message()
    for key, value in scope["headers"]:
        name = key.decode("latin-1")
        if name.lower() in ("content-length", "transfer-encoding"):
            continue
        msg.add_header(name, value.decode("latin-1"))
    if body or scope["method"] in ("POST", "PUT"):
        msg.add_header("Content-Length", str(len(body)))
    return msg


def make_legacy_endpoint(generator, static_dir: Path, db_path: str):
    async def legacy(request: Request):
        scope = request.scope
        body = await request.body()
        target = scope["raw_path"].decode("latin-1")
        if scope["query_string"]:
            target += "?" + scope["query_string"].decode("latin-1")
        adapted = {
            "method": scope["method"],
            "target": target,
            "headers": _message_headers(scope, body),
            "body": body,
            "client": tuple(scope["client"]) if scope.get("client") else ("", 0),
        }

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        pipe = _Pipe(loop, queue)
        ctx = contextvars.copy_context()

        def run():
            try:
                ctx.run(_AdaptedHandler, generator, static_dir, db_path,
                        request=adapted, pipe=pipe)
            except BaseException as exc:
                traceback.print_exc(file=sys.stderr)
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=run, daemon=True).start()

        buf = b""
        while b"\r\n\r\n" not in buf:
            item = await queue.get()
            if item is None:
                raise RuntimeError("legacy handler wrote no response")
            if isinstance(item, BaseException):
                raise item
            buf += item
        head, _, first = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status = int(lines[0].split()[1])
        headers = []
        for line in lines[1:]:
            name, _, value = line.partition(b":")
            if name.strip().lower().decode("latin-1") not in _SERVER_OWNED:
                headers.append((name.strip().lower(), value.strip()))

        async def body_iter():
            if first:
                yield first
            while True:
                chunk = await queue.get()
                if chunk is None:
                    return
                if isinstance(chunk, BaseException):
                    raise chunk
                yield chunk

        response = StreamingResponse(body_iter(), status_code=status)
        response.raw_headers = headers
        return response

    return legacy


async def _health(request: Request):
    return JSONResponse({"ok": True, "build": os.environ.get("MTGC_BUILD_ID") or None})


def create_app(generator, static_dir: Path, db_path: str, resolver=None,
               multi: bool = False) -> FastAPI:
    """The app: tenant middleware in front, the legacy adapter behind every path."""
    # No /docs, /redoc or /openapi.json yet: the legacy server never served
    # them, and the adapter must see every path it served.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TenantMiddleware, resolver=resolver or SingleTenantResolver(),
                       multi=multi)
    app.add_route("/health", _health, methods=["GET"], include_in_schema=False)
    # Native families first; Starlette matches in registration order, so
    # anything they do not claim falls through to the adapter below.
    app.include_router(collection_routes.create_router(db_path))
    app.add_route(
        "/{path:path}",
        make_legacy_endpoint(generator, static_dir, db_path),
        methods=LEGACY_METHODS,
        include_in_schema=False,
    )
    return app
