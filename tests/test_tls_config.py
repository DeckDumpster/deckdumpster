"""Externally-provided TLS certificates: MTGC_TLS_CERT / MTGC_TLS_KEY."""

import http.client
import shutil
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from mtg_collector.cli.crack_pack_server import (
    _build_tls_context,
    _resolve_external_tls_paths,
)

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl is required to mint test certificates"
)


def _mint_cert(tmp_path, cn):
    """Generate a self-signed cert/key pair with the given common name."""
    cert = tmp_path / f"{cn}.pem"
    key = tmp_path / f"{cn}-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes",
            "-subj", f"/CN={cn}",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("MTGC_TLS_CERT", raising=False)
    monkeypatch.delenv("MTGC_TLS_KEY", raising=False)
    return monkeypatch


# --- The four cases from the spec -------------------------------------------


def test_neither_set_means_unchanged(clean_env):
    """UNSET MEANS UNCHANGED: no external cert, caller auto-generates as before."""
    assert _resolve_external_tls_paths() is None


def test_both_set_uses_them(clean_env, tmp_path):
    cert, key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_CERT", str(cert))
    clean_env.setenv("MTGC_TLS_KEY", str(key))

    assert _resolve_external_tls_paths() == (cert, key)


def test_only_cert_set_raises(clean_env, tmp_path):
    cert, _key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_CERT", str(cert))

    with pytest.raises(ValueError, match="MTGC_TLS_KEY"):
        _resolve_external_tls_paths()


def test_only_key_set_raises(clean_env, tmp_path):
    _cert, key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_KEY", str(key))

    with pytest.raises(ValueError, match="MTGC_TLS_CERT"):
        _resolve_external_tls_paths()


@pytest.mark.parametrize("broken", ["MTGC_TLS_CERT", "MTGC_TLS_KEY"])
def test_unreadable_path_raises_no_silent_downgrade(clean_env, tmp_path, broken):
    """A missing path must raise, never quietly fall back to self-signed."""
    cert, key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_CERT", str(cert))
    clean_env.setenv("MTGC_TLS_KEY", str(key))
    clean_env.setenv(broken, str(tmp_path / "does-not-exist.pem"))

    with pytest.raises(ValueError, match=broken):
        _resolve_external_tls_paths()


# --- Auto-generation path stays untouched when the vars are unset ------------


def test_context_autogenerates_when_unset(clean_env, tmp_path):
    ctx = _build_tls_context(tmp_path)

    assert isinstance(ctx, ssl.SSLContext)
    assert (tmp_path / "server.pem").is_file()
    assert (tmp_path / "server-key.pem").is_file()


def test_context_does_not_generate_when_external(clean_env, tmp_path):
    cert, key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_CERT", str(cert))
    clean_env.setenv("MTGC_TLS_KEY", str(key))

    _build_tls_context(tmp_path)

    assert not (tmp_path / "server.pem").exists()
    assert not (tmp_path / "server-key.pem").exists()


# --- End to end: the server actually serves the supplied certificate --------


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def test_server_serves_the_external_certificate(clean_env, tmp_path):
    """The served cert is the operator's, not CN=mtgc-local."""
    cert, key = _mint_cert(tmp_path, "mtgc-external")
    clean_env.setenv("MTGC_TLS_CERT", str(cert))
    clean_env.setenv("MTGC_TLS_KEY", str(key))

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.socket = _build_tls_context(tmp_path).wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        client_ctx = ssl.create_default_context(cafile=str(cert))
        conn = http.client.HTTPSConnection("localhost", port, context=client_ctx, timeout=10)
        conn.connect()
        served = dict(x[0] for x in conn.sock.getpeercert()["subject"])
        conn.request("GET", "/")
        assert conn.getresponse().read() == b"ok"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert served["commonName"] == "mtgc-external"
    assert served["commonName"] != "mtgc-local"


def test_self_signed_default_is_not_the_external_cert(clean_env, tmp_path):
    """Sanity: with the vars unset the server still serves CN=mtgc-local."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.socket = _build_tls_context(tmp_path).wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        client_ctx = ssl.create_default_context(cafile=str(tmp_path / "server.pem"))
        with socket.create_connection(("localhost", port), timeout=10) as sock:
            with client_ctx.wrap_socket(sock, server_hostname="localhost") as tls:
                served = dict(x[0] for x in tls.getpeercert()["subject"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert served["commonName"] == "mtgc-local"
