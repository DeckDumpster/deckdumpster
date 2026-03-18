"""Shared HTTP client for commander scripts talking to the MTGC web API."""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HOST = "https://localhost:8081"
_HOST_CONFIG = os.path.join(os.path.dirname(__file__), "..", "host")


def _read_host_config():
    """Read host from .claude/skills/jumpstart/host file if it exists."""
    try:
        with open(_HOST_CONFIG) as f:
            host = f.read().strip()
            if host:
                return host
    except FileNotFoundError:
        pass
    return None


def parse_host_arg(argv):
    """Strip --host <url> from argv. Returns (base_url, remaining_argv).

    Priority: --host flag > MTGC_HOST env > jumpstart/host file > DEFAULT_HOST.
    """
    base_url = _read_host_config() or DEFAULT_HOST
    base_url = os.environ.get("MTGC_HOST", base_url)
    remaining = [argv[0]]
    i = 1
    while i < len(argv):
        if argv[i] == "--host" and i + 1 < len(argv):
            base_url = argv[i + 1]
            i += 2
        else:
            remaining.append(argv[i])
            i += 1
    return base_url, remaining


class DeckBuilderClient:
    """HTTP client for the MTGC deck-builder API."""

    def __init__(self, base_url=None):
        url = (base_url or DEFAULT_HOST).rstrip("/")
        # Bare hostname/IP → add https:// and default port
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        # If no port specified and using default https, add default MTGC port
        parts = urllib.parse.urlparse(url)
        if not parts.port:
            url = f"{parts.scheme}://{parts.hostname}:8080"
        self.base_url = url
        # Accept self-signed certs
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def get(self, path, params=None):
        """GET request. Returns parsed JSON."""
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        return self._do(req)

    def post(self, path, body=None):
        """POST request with JSON body. Returns parsed JSON."""
        url = self.base_url + path
        data = json.dumps(body or {}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        return self._do(req)

    def put(self, path, body=None):
        """PUT request with JSON body. Returns parsed JSON."""
        url = self.base_url + path
        data = json.dumps(body or {}).encode()
        req = urllib.request.Request(url, data=data, method="PUT")
        req.add_header("Content-Type", "application/json")
        return self._do(req)

    def _do(self, req):
        """Execute request, return parsed JSON or raise."""
        try:
            resp = urllib.request.urlopen(req, context=self._ctx)
            body = resp.read()
            if not body:
                return None
            return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                err = json.loads(body)
                msg = err.get("error", body)
            except json.JSONDecodeError:
                msg = body
            print(f"API error ({e.code}): {msg}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"Connection error: {e.reason}", file=sys.stderr)
            print(f"Is the server running at {self.base_url}?", file=sys.stderr)
            sys.exit(1)
