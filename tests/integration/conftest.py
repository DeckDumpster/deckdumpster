"""
Shared fixtures for integration tests.

These tests run against a live container instance with the demo dataset.
The instance must already be running — use deploy scripts to set it up:

    bash deploy/setup.sh integration-test --init
    systemctl --user start mtgc-integration-test

Or pass an existing instance via --instance:

    uv run pytest tests/integration/ --instance sealed-collection

The fixture discovers the port automatically via `podman port`.
"""

import json
import subprocess
import urllib.request
import ssl

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--instance",
        default="integration-test",
        help="Container instance name to test against (default: integration-test)",
    )


@pytest.fixture(scope="session")
def instance_name(request):
    return request.config.getoption("--instance")


def _discover_container(instance_name):
    """Try both container name patterns: systemd-mtgc-{name} (Linux) and mtgc-{name} (macOS)."""
    for candidate in [f"systemd-mtgc-{instance_name}", f"mtgc-{instance_name}"]:
        try:
            subprocess.run(
                ["podman", "container", "exists", candidate],
                capture_output=True, check=True,
            )
            return candidate
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


@pytest.fixture(scope="session")
def base_url(instance_name):
    """Discover the HTTPS base URL for the running container instance."""
    container_name = _discover_container(instance_name)
    if container_name is None:
        pytest.skip(
            f"No container found for instance '{instance_name}'. "
            f"Start it with: bash deploy/setup.sh {instance_name} --init && "
            f"systemctl --user start mtgc-{instance_name}"
        )

    try:
        result = subprocess.run(
            ["podman", "port", container_name, "8081/tcp"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"Could not query port for '{container_name}'")

    port_line = result.stdout.strip()
    if not port_line:
        pytest.skip(f"Could not determine port for '{container_name}'")

    # Parse "0.0.0.0:36305" -> 36305
    port = port_line.split(":")[-1]
    url = f"https://localhost:{port}"

    # Verify the instance is actually responding
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(f"{url}/")
        urllib.request.urlopen(req, context=ctx, timeout=5)
    except Exception:
        pytest.skip(f"Instance at {url} not responding")

    return url


@pytest.fixture(scope="session")
def api(base_url):
    """HTTP client for making API requests to the test instance."""
    return APIClient(base_url)


# DB paths inside the container (data volume mount point).
_CONTAINER_DB = "/data/collection.sqlite"
_CONTAINER_DB_BACKUP = "/data/collection.sqlite.integ.bak"
_CONTAINER_SHARED_DB = "/data/shared.sqlite"
_CONTAINER_SHARED_DB_BACKUP = "/data/shared.sqlite.integ.bak"

# Snapshot before the suite, restore after. Mirrors tests/ui/conftest.py's
# per-test isolation, but at SESSION scope: integration deliberately exercises
# real mutations and tests may depend on each other's writes within the run, so
# we don't restore between tests — only once at the end, to hand the container
# back in fixture state. Without this, mutations here (notably test_fetch_prices,
# which live-fetches TCGCSV prices into the shared sealed_prices table) survive
# into a subsequent `pytest tests/ui/` run against the same container, whose
# session snapshot then captures the polluted prices — silently breaking sealed
# UI scenarios that assert on fixture prices.
#
# Both collection.sqlite and shared.sqlite are covered (shared holds sealed_prices
# and latest_* views). Uses sqlite3.backup() in both directions rather than cp:
# under WAL the live .sqlite is one of three files, and a cp leaves the -wal
# sidecar so the server keeps reading stale frames. backup() copies pages through
# SQLite's locking protocol.
_INTEG_BACKUP_CMD = (
    f'python3 -c "import sqlite3, os; '
    f"s=sqlite3.connect('{_CONTAINER_DB}'); "
    f"d=sqlite3.connect('{_CONTAINER_DB_BACKUP}'); "
    f"s.backup(d); s.close(); d.close(); "
    f"p='{_CONTAINER_SHARED_DB}'; "
    f"b='{_CONTAINER_SHARED_DB_BACKUP}'; "
    f"exec('if os.path.exists(p):\\n s=sqlite3.connect(p)\\n d=sqlite3.connect(b)\\n s.backup(d)\\n s.close()\\n d.close()')"
    '"'
)
_INTEG_RESTORE_CMD = (
    f'python3 -c "import sqlite3, os; '
    f"s=sqlite3.connect('{_CONTAINER_DB_BACKUP}'); "
    f"d=sqlite3.connect('{_CONTAINER_DB}'); "
    f"s.backup(d); s.close(); d.close(); "
    f"p='{_CONTAINER_SHARED_DB_BACKUP}'; "
    f"q='{_CONTAINER_SHARED_DB}'; "
    f"exec('if os.path.exists(p):\\n s=sqlite3.connect(p)\\n d=sqlite3.connect(q)\\n s.backup(d)\\n s.close()\\n d.close()')"
    '"'
)


@pytest.fixture(scope="session", autouse=True)
def _restore_container_after_suite(instance_name):
    """Snapshot the container's DBs before the suite and restore them after.

    No-op when there is no container (the skip path), so local runs against a
    remote/base URL are unaffected.
    """
    container = _discover_container(instance_name)
    if container is None:
        yield
        return
    snapshot = subprocess.run(
        ["podman", "exec", container, "bash", "-c", _INTEG_BACKUP_CMD],
        capture_output=True, text=True,
    )
    # If the snapshot itself failed, don't pretend we can restore — fail loudly
    # rather than silently leaving the container polluted for later suites.
    snapshot.check_returncode()
    yield
    subprocess.run(
        ["podman", "exec", container, "bash", "-c", _INTEG_RESTORE_CMD],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["podman", "exec", container, "rm", "-f",
         _CONTAINER_DB_BACKUP, _CONTAINER_SHARED_DB_BACKUP],
        capture_output=True,
    )


class APIClient:
    """Minimal HTTP client for integration tests (no external deps)."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def get(self, path: str) -> tuple:
        """GET request. Returns (status_code, parsed_json)."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, context=self._ctx, timeout=30)
            body = json.loads(resp.read())
            return resp.status, body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            return e.code, body

    def get_raw(self, path: str) -> tuple:
        """GET request returning raw bytes — used for non-JSON assets
        like CSS, fonts, images. Returns (status_code, body_bytes)."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, context=self._ctx, timeout=30)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path: str, data: dict, timeout: int = 30) -> tuple:
        """POST JSON request. Returns (status_code, parsed_json)."""
        return self._json_request("POST", path, data, timeout=timeout)

    def put(self, path: str, data: dict) -> tuple:
        """PUT JSON request. Returns (status_code, parsed_json)."""
        return self._json_request("PUT", path, data)

    def delete(self, path: str) -> tuple:
        """DELETE request. Returns (status_code, parsed_json)."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            resp = urllib.request.urlopen(req, context=self._ctx, timeout=30)
            body = json.loads(resp.read())
            return resp.status, body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            return e.code, body

    def _json_request(self, method: str, path: str, data: dict, timeout: int = 30) -> tuple:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, context=self._ctx, timeout=timeout)
            resp_body = json.loads(resp.read())
            return resp.status, resp_body
        except urllib.error.HTTPError as e:
            resp_body = json.loads(e.read())
            return e.code, resp_body
