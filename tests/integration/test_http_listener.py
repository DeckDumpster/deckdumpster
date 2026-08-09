"""
Integration test: the optional plain-HTTP listener inside a real container.

The dual-listener feature has two independent halves, and BOTH must be present
for this file to assert anything:

  * ``MTGC_HTTP_PORT=8080`` in ``~/.config/mtgc/<instance>.env`` — makes the
    server bind a second, plain listener on container port 8080.
  * ``bash deploy/setup.sh <instance> --test --http-port <p>`` — publishes that
    container port on the host, loopback only (``127.0.0.1:<p>:8080``).

They are deliberately decoupled: enabling the listener on an instance is an
env-file edit, publishing it is a quadlet render. This file keys off the
publish, because that is what makes the listener reachable from the test.

**Skips cleanly when no plaintext port is published**, so it is a no-op against
every existing instance and against CI's ``ci-test``, which passes no
``--http-port``. When the port IS published, the listener is expected to answer
— a published port with nothing behind it is a broken instance, not a reason to
skip.

Read-only: every request here is ``GET /``. Nothing mutates the DB, so
conftest.py's session snapshot/restore is untouched.

To exercise for real:

    bash deploy/setup.sh tlstest --test --http-port 8083
    echo 'MTGC_HTTP_PORT=8080' >> ~/.config/mtgc/tlstest.env
    systemctl --user restart mtgc-tlstest
    uv run pytest tests/integration/test_http_listener.py -v --instance tlstest
"""

import subprocess
import urllib.request

import pytest

from tests.integration.conftest import _discover_container

# The container-internal port the plain listener binds (the CLI's own default).
# 8081 is the TLS listener and the only EXPOSEd port.
_CONTAINER_PLAIN_PORT = "8080/tcp"


@pytest.fixture(scope="session")
def plain_publish(instance_name):
    """The host-side publish of the container's plaintext port, e.g. "127.0.0.1:8083".

    Skips the whole module when the instance publishes no such port.
    """
    container = _discover_container(instance_name)
    if container is None:
        pytest.skip(f"No container found for instance '{instance_name}'")

    result = subprocess.run(
        ["podman", "port", container, _CONTAINER_PLAIN_PORT],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip(
            f"Instance '{instance_name}' publishes no plaintext port — "
            f"set it up with: bash deploy/setup.sh {instance_name} --test --http-port <p>"
        )

    return result.stdout.strip().splitlines()[0].strip()


@pytest.fixture(scope="session")
def plain_url(plain_publish):
    """http://127.0.0.1:<published port>.

    Literal 127.0.0.1, not "localhost": the publish is loopback-IPv4 only, and
    "localhost" can resolve to ::1 first.
    """
    port = plain_publish.rsplit(":", 1)[-1]
    return f"http://127.0.0.1:{port}"


def _get_status(url):
    resp = urllib.request.urlopen(urllib.request.Request(url), timeout=10)
    return resp.status


class TestPlainHTTPListener:
    """Both listeners answer, in the same run, from the same container."""

    def test_plain_listener_serves_http(self, plain_url):
        """The published plaintext port serves the app over http://."""
        assert _get_status(f"{plain_url}/") == 200

    def test_https_listener_still_serves(self, plain_publish, api):
        """Adding the plain listener does not take HTTPS away from LAN clients.

        Depends on plain_publish so it asserts only when the feature is on —
        the point is that BOTH are true in the same run, on one container.
        """
        status, body = api.get_raw("/")
        assert status == 200
        assert body

    def test_plain_port_is_published_on_loopback_only(self, plain_publish):
        """The plaintext publish binds 127.0.0.1, never 0.0.0.0.

        A 0.0.0.0 publish would put plaintext on the LAN. The binding is
        hardcoded in deploy/render-quadlet.sh and is not operator-supplied;
        this is the guard on that.
        """
        bind_address = plain_publish.rsplit(":", 1)[0]
        assert bind_address == "127.0.0.1", (
            f"plaintext port published on {plain_publish} — expected a 127.0.0.1 bind"
        )
