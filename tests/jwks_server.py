"""A real JWKS server and token minter for the isolation gate (sp-0knuwi).

Not a fake `fetch`: this binds a loopback port and serves `/certs` over HTTP, so
the verifier's own `urllib` fetch, JWKS caching and kid handling are what run.

Two uses:

* in-process, as a context manager (`with JwksServer() as jwks:`), for the pytest
  isolation suite;
* as a script, `python tests/jwks_server.py serve DIR EMAIL...`, for
  `deploy/handles.sh`, which needs tokens a container can present. It writes
  `DIR/url`, `DIR/token.<email>` for each email, and `DIR/token.expired` and
  `DIR/token.badsig` (signed by a key the server does not publish), then serves
  until killed.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISS = "https://gate.cloudflareaccess.com"
AUD = "gate-aud-tag"
KID = "gate-key-1"


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class JwksServer:
    def __init__(self):
        self.key = _new_key()
        self.unpublished_key = _new_key()
        self.fetches = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/certs":
                    self.send_error(404)
                    return
                owner.fetches += 1
                body = json.dumps({"keys": [owner.jwk()]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def jwk(self) -> dict:
        d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        d.update(kid=KID, alg="RS256", use="sig")
        return d

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/certs"

    @property
    def env(self) -> dict:
        return {
            "MTGC_ACCESS_TEAM_DOMAIN": ISS,
            "MTGC_ACCESS_AUD": AUD,
            "MTGC_ACCESS_JWKS_URL": self.url,
        }

    def token(self, email: str | None = "a@x.org", *, key=None, kid: str = KID, **over) -> str:
        now = int(time.time())
        claims = {"iss": ISS, "aud": [AUD], "iat": now, "exp": now + 600}
        if email is not None:
            claims["email"] = email
        claims.update(over)
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": kid})

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


def _serve(directory: str, emails: list[str]) -> None:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    with JwksServer() as jwks:
        (out / "url").write_text(jwks.url)
        for email in emails:
            (out / f"token.{email}").write_text(jwks.token(email))
        (out / "token.expired").write_text(
            jwks.token(emails[0], exp=int(time.time()) - 60))
        (out / "token.badsig").write_text(jwks.token(emails[0], key=jwks.unpublished_key))
        (out / "ready").write_text("1")
        threading.Event().wait()


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "serve":
        raise SystemExit("usage: jwks_server.py serve DIR EMAIL...")
    _serve(sys.argv[2], sys.argv[3:])
