"""Listener wiring: MTGC_HTTP_PORT and the optional second, plain-HTTP listener.

Tier 1 — no container, no network, no fixed port. Every listener is bound on
port 0 so the suite never collides with a running instance.

The load-bearing assertion is UNSET MEANS UNCHANGED: with ``MTGC_HTTP_PORT``
absent, ``run()`` constructs exactly ONE listener, exactly as it did before the
option existed. Everything else here is a variation on that.
"""

import argparse
import contextlib
import http.client
import shutil
import ssl
import subprocess
import threading
import time

import pytest

from mtg_collector.cli import crack_pack_server as cps

# How long startup (schema migration + bind) is allowed to take.
_STARTUP_TIMEOUT = 30.0


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Isolate the process env and filesystem the server reads at startup.

    ``MTGC_HOME`` points at a scratch dir so the MTGJSON auto-import branch
    finds no AllPrintings.json and merely warns, and so self-signed certs (if
    any test reaches that path) land in the tmpdir.
    """
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    for var in ("MTGC_HTTP_PORT", "MTGC_TLS_CERT", "MTGC_TLS_KEY", "MTGC_SHARED_DB", "MTGC_DB"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@contextlib.contextmanager
def _server_process(monkeypatch, tmp_path, https=False):
    """Run ``crack_pack_server.run()`` in a thread, recording every listener.

    Yields ``(created, error, thread)`` where ``created`` is the list of
    ``ThreadingHTTPServer`` instances the wiring actually constructed, in
    construction order, and ``error`` collects anything ``run()`` raised.
    """
    created = []
    real_server_cls = cps.ThreadingHTTPServer

    def recording(address, handler):
        server = real_server_cls(address, handler)
        created.append(server)
        return server

    monkeypatch.setattr(cps, "ThreadingHTTPServer", recording)

    args = argparse.Namespace(db=str(tmp_path / "collection.sqlite"), port=0, https=https)
    error = []

    def target():
        try:
            cps.run(args)
        except BaseException as exc:  # re-raised by the assertions below
            error.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    try:
        yield created, error, thread
    finally:
        for server in created:
            # shutdown() blocks until serve_forever() acknowledges, and
            # serve_forever() may never have started — bound the wait.
            stopper = threading.Thread(target=server.shutdown, daemon=True)
            stopper.start()
            stopper.join(timeout=5)
            with contextlib.suppress(Exception):
                server.server_close()
        if cps._ingest_executor is not None:
            cps._ingest_executor.shutdown(wait=False)
        thread.join(timeout=10)


def _get_root(server, scheme):
    """GET / against a bound listener, returning the HTTP status code."""
    port = server.server_address[1]
    if scheme == "https":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=5)
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/")
        return conn.getresponse().status
    finally:
        conn.close()


def _wait_for_listeners(created, count, error, timeout=_STARTUP_TIMEOUT):
    """Block until at least ``count`` listeners have been constructed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if error:
            raise AssertionError(f"run() raised before binding {count} listener(s): {error[0]!r}")
        if len(created) >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"only {len(created)} listener(s) constructed, expected {count}")


def _wait_for_root(server, scheme, timeout=_STARTUP_TIMEOUT):
    """Block until the listener answers GET /, returning the status code."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            return _get_root(server, scheme)
        except Exception as exc:
            last = exc
            time.sleep(0.05)
    raise AssertionError(f"{scheme} listener never answered GET /: {last!r}")


# --- The three cases from the spec ------------------------------------------


def test_unset_constructs_a_single_listener(clean_env, tmp_path):
    """UNSET MEANS UNCHANGED: no MTGC_HTTP_PORT, no second listener."""
    with _server_process(clean_env, tmp_path) as (created, error, _thread):
        _wait_for_listeners(created, 1, error)
        # Answering proves run() is past the construction point, so the count
        # below is final rather than a race with a slow second bind.
        assert _wait_for_root(created[0], "http") == 200
        assert len(created) == 1, f"expected one listener, got {len(created)}"


def test_http_port_zero_adds_a_second_listener(clean_env, tmp_path):
    """MTGC_HTTP_PORT=0 (OS-assigned): both listeners bind and both answer."""
    clean_env.setenv("MTGC_HTTP_PORT", "0")
    with _server_process(clean_env, tmp_path) as (created, error, _thread):
        _wait_for_listeners(created, 2, error)
        primary, plain = created
        assert _wait_for_root(primary, "http") == 200
        assert _wait_for_root(plain, "http") == 200
        # Distinct OS-assigned ports, neither of them 0.
        ports = {primary.server_address[1], plain.server_address[1]}
        assert 0 not in ports
        assert len(ports) == 2


@pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl is required to mint a test certificate"
)
def test_dual_listen_serves_tls_and_plain_side_by_side(clean_env, tmp_path):
    """The point of the feature: HTTPS for LAN clients, http:// for the tunnel."""
    cert = tmp_path / "listener.pem"
    key = tmp_path / "listener-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes",
            "-subj", "/CN=mtgc-listener-test",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    clean_env.setenv("MTGC_TLS_CERT", str(cert))
    clean_env.setenv("MTGC_TLS_KEY", str(key))
    clean_env.setenv("MTGC_HTTP_PORT", "0")

    with _server_process(clean_env, tmp_path, https=True) as (created, error, _thread):
        _wait_for_listeners(created, 2, error)
        tls_server, plain_server = created
        assert _wait_for_root(tls_server, "https") == 200
        assert _wait_for_root(plain_server, "http") == 200
        # The plain listener must NOT have been wrapped in TLS.
        with pytest.raises(Exception):
            _get_root(plain_server, "https")


def test_non_integer_http_port_raises_and_binds_nothing(clean_env, tmp_path):
    """A typo'd port is a hard failure — never a silent fall back to one listener."""
    clean_env.setenv("MTGC_HTTP_PORT", "eighty-eighty")
    with _server_process(clean_env, tmp_path) as (created, error, thread):
        thread.join(timeout=_STARTUP_TIMEOUT)
        assert not thread.is_alive(), "run() should have exited with an error"
        assert error, "non-integer MTGC_HTTP_PORT was swallowed"
        assert isinstance(error[0], ValueError)
        assert "eighty-eighty" in str(error[0])
        assert created == [], "nothing should bind when the port is unparseable"
