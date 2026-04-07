"""
Shared fixtures for UI scenario tests.

These tests run against a live container instance (same as integration tests).
The instance must already be running:

    bash deploy/setup.sh ui-test --init
    systemctl --user start mtgc-ui-test

Or pass an existing instance via --instance:

    uv run pytest tests/ui/ -v --instance my-instance
"""

import logging
import ssl
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

# DB paths inside the container (data volume mount point).
_CONTAINER_DB = "/data/collection.sqlite"
_CONTAINER_DB_BACKUP = "/data/collection.sqlite.bak"
_CONTAINER_SHARED_DB = "/data/shared.sqlite"
_CONTAINER_SHARED_DB_BACKUP = "/data/shared.sqlite.bak"

# Backup uses sqlite3.backup() for safe snapshot with open server connections.
# Restore uses cp — fast and safe because the server opens fresh connections
# (with fresh ATTACH) per request, so no stale handles.
# Both collection.sqlite and shared.sqlite are backed up and restored,
# since tests may write to shared tables (e.g. price seeding).
_BACKUP_CMD = (
    f'python3 -c "import sqlite3, os; '
    f"s=sqlite3.connect('{_CONTAINER_DB}'); "
    f"d=sqlite3.connect('{_CONTAINER_DB_BACKUP}'); "
    f"s.backup(d); s.close(); d.close(); "
    f"p='{_CONTAINER_SHARED_DB}'; "
    f"b='{_CONTAINER_SHARED_DB_BACKUP}'; "
    f"exec('if os.path.exists(p):\\n s=sqlite3.connect(p)\\n d=sqlite3.connect(b)\\n s.backup(d)\\n s.close()\\n d.close()')"
    '"'
)
_RESTORE_CMD = (
    f"cp {_CONTAINER_DB_BACKUP} {_CONTAINER_DB}"
    f" && {{ [ -f {_CONTAINER_SHARED_DB_BACKUP} ] && cp {_CONTAINER_SHARED_DB_BACKUP} {_CONTAINER_SHARED_DB}; true; }}"
)


def pytest_addoption(parser):
    # Guard: option may already be registered by tests/integration/conftest.py
    # when both test directories are collected together.
    for opt_args, opt_kwargs in [
        (["--instance"], dict(
            default="integration-test",
            help="Container instance name to test against (default: integration-test)",
        )),
        (["--base-url"], dict(
            default=None,
            help="Base URL to test against directly, skipping container discovery (e.g. http://localhost:8000)",
        )),
        (["--generate"], dict(
            default=None,
            help="Generate implementation for a specific intent name",
        )),
        (["--generate-missing"], dict(
            action="store_true",
            default=False,
            help="Generate implementations for all intents that lack one",
        )),
        (["--regenerate"], dict(
            default=None,
            help="Force-regenerate implementation for a specific intent name",
        )),
        (["--regenerate-all"], dict(
            action="store_true",
            default=False,
            help="Force-regenerate all implementations",
        )),
        (["--diagnose"], dict(
            action="store_true",
            default=False,
            help="On replay failure, run conflict resolver to diagnose the cause",
        )),
        (["--intents-only"], dict(
            action="store_true",
            default=False,
            help="Force all tests through Claude harness, ignoring implementations",
        )),
    ]:
        try:
            parser.addoption(*opt_args, **opt_kwargs)
        except ValueError:
            pass


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
def container_name(request, instance_name):
    """Resolve and expose the container name for DB snapshot/restore.

    Returns None when --base-url is provided (no container needed).
    """
    if request.config.getoption("--base-url"):
        return None
    name = _discover_container(instance_name)
    if name is None:
        pytest.skip(
            f"No container found for instance '{instance_name}'. "
            f"Start it with: bash deploy/setup.sh {instance_name} --init && "
            f"systemctl --user start mtgc-{instance_name}"
        )
    return name


@pytest.fixture(scope="session")
def base_url(request, instance_name, container_name):
    """Discover the base URL for the running server.

    Use --base-url to point at a local dev server directly (e.g.
    http://localhost:8000), or --instance for Podman container discovery.
    """
    explicit = request.config.getoption("--base-url")
    if explicit:
        # Verify the instance is responding.
        try:
            req = urllib.request.Request(f"{explicit}/")
            kwargs = {"timeout": 5}
            if explicit.startswith("https"):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                kwargs["context"] = ctx
            urllib.request.urlopen(req, **kwargs)
        except Exception:
            pytest.skip(f"Server at {explicit} not responding")
        return explicit

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

    port = port_line.split(":")[-1]
    url = f"https://localhost:{port}"

    # Verify the instance is responding.
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
def _db_snapshot(container_name):
    """Create a one-time DB snapshot at session start for per-test restore.

    No-op when running against a local server (--base-url, no container).
    """
    if container_name is None:
        yield None
        return
    log.info("Creating DB snapshot in container %s", container_name)
    subprocess.run(
        ["podman", "exec", container_name, "bash", "-c", _BACKUP_CMD],
        check=True, capture_output=True, text=True,
    )
    yield container_name
    # Clean up the backup file.
    subprocess.run(
        ["podman", "exec", container_name, "rm", "-f", _CONTAINER_DB_BACKUP],
        capture_output=True,
    )


@pytest.fixture(autouse=True)
def _restore_db(_db_snapshot):
    """Restore the DB to its snapshot state after each test.

    No-op when running against a local server (--base-url, no container).
    """
    yield
    container = _db_snapshot
    if container is None:
        return
    log.info("Restoring DB snapshot in container %s", container)
    subprocess.run(
        ["podman", "exec", container, "bash", "-c", _RESTORE_CMD],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="session")
def screenshot_dir():
    """Create a timestamped screenshot output directory."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = Path("screenshots") / "ui" / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def browser():
    """Launch headless Chromium that accepts self-signed certs."""
    pw = sync_playwright().start()
    b = pw.chromium.launch(
        headless=True,
        args=["--ignore-certificate-errors"],
    )
    yield b
    b.close()
    pw.stop()


@pytest.fixture
def page(browser):
    """Fresh browser page per test (isolated context)."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        ignore_https_errors=True,
    )
    p = context.new_page()
    yield p
    context.close()
