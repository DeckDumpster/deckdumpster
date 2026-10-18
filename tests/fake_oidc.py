"""An in-process OIDC provider (discovery, JWKS, token endpoint) for sign-in tests.

Real HTTP on a loopback port, so the module's own discovery, JWKS and token-exchange
code is what runs. ``grant(...)`` registers the claims a code will exchange for.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "fake-key-1"
CLIENT_ID = "deckdumpster"


class FakeProvider:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.codes: dict[str, dict] = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, body):
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/.well-known/openid-configuration":
                    self._json({"issuer": owner.issuer,
                                "authorization_endpoint": owner.issuer + "/authorize",
                                "token_endpoint": owner.issuer + "/token",
                                "jwks_uri": owner.issuer + "/jwks"})
                elif self.path == "/jwks":
                    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.server_key()))
                    jwk.update(kid=KID, alg="RS256", use="sig")
                    self._json({"keys": [jwk]})
                else:
                    self.send_error(404)

            def server_key(self):
                return owner.key.public_key()

            def do_POST(self):
                size = int(self.headers["Content-Length"])
                form = urllib.parse.parse_qs(self.rfile.read(size).decode())
                code = form["code"][0]
                if code not in owner.codes:
                    self.send_error(400)
                    return
                claims = owner.codes.pop(code)
                now = int(time.time())
                body = {"iss": owner.issuer, "aud": form["client_id"][0],
                        "iat": now, "exp": now + 300, **claims}
                token = jwt.encode(body, owner.key, algorithm="RS256", headers={"kid": KID})
                self._json({"id_token": token, "access_token": "unused"})

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def issuer(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def grant(self, code: str, **claims) -> None:
        self.codes[code] = claims

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
