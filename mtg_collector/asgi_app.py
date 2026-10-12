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
import sys
import threading
import traceback
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import StreamingResponse

from mtg_collector.cli.crack_pack_server import CrackPackHandler
from mtg_collector.tenancy import SingleTenantResolver, bind

LEGACY_METHODS = ["GET", "POST", "PUT", "DELETE"]

# The handler writes a raw HTTP/1.1 response; these are the framing headers the
# ASGI server owns and would otherwise duplicate or contradict.
_SERVER_OWNED = {"connection", "keep-alive", "transfer-encoding", "server", "date"}


class TenantMiddleware:
    """Resolve the tenant, bind it, run the request inside the binding."""

    def __init__(self, app, resolver):
        self.app = app
        self.resolver = resolver

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        with bind(self.resolver.resolve(scope)):
            await self.app(scope, receive, send)


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


def create_app(generator, static_dir: Path, db_path: str, resolver=None) -> FastAPI:
    """The app: tenant middleware in front, the legacy adapter behind every path."""
    # No /docs, /redoc or /openapi.json yet: the legacy server never served
    # them, and the adapter must see every path it served.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TenantMiddleware, resolver=resolver or SingleTenantResolver())
    app.add_route(
        "/{path:path}",
        make_legacy_endpoint(generator, static_dir, db_path),
        methods=LEGACY_METHODS,
        include_in_schema=False,
    )
    return app
