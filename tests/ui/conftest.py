"""
Shared fixtures for UI scenario tests.

These tests run against a live container instance (same as integration tests).
The instance must already be running:

    bash deploy/setup.sh ui-test --init
    systemctl --user start mtgc-ui-test

Or pass an existing instance via --instance:

    uv run pytest tests/ui/ -v --instance my-instance
"""

import ssl
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


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
def base_url(request, instance_name):
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
