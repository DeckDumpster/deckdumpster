"""Authenticated encryption for a tenant's secret (their Anthropic API key).

Stdlib only: encrypt-then-MAC over an HMAC-SHA256 counter keystream, with
independent encryption and MAC keys derived from the master key and a fresh
random nonce per message. The ciphertext is bound to the tenant's database_id
as associated data, so a blob copied between rows fails to open.

The master key comes from the environment (MTGC_MASTER_KEY, or a file named by
MTGC_MASTER_KEY_FILE) and is never stored in the registry beside the
ciphertext.
"""

import base64
import hashlib
import hmac
import os
import secrets

_VERSION = b"\x01"
_NONCE = 16
_TAG = 32


class MasterKeyError(Exception):
    """The master key is missing, malformed, or does not open the ciphertext."""


def master_key() -> bytes:
    raw = os.environ.get("MTGC_MASTER_KEY")
    path = os.environ.get("MTGC_MASTER_KEY_FILE")
    if raw and path:
        raise MasterKeyError("set only one of MTGC_MASTER_KEY and MTGC_MASTER_KEY_FILE")
    if path:
        raw = open(path, encoding="ascii").read().strip()
    if not raw:
        raise MasterKeyError("no master key: set MTGC_MASTER_KEY or MTGC_MASTER_KEY_FILE")
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:
        raise MasterKeyError("master key is not urlsafe base64") from exc
    if len(key) != 32:
        raise MasterKeyError("master key must decode to 32 bytes")
    return key


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _subkeys(master: bytes) -> tuple[bytes, bytes]:
    return (
        hmac.new(master, b"mtgc-tenant-key/enc", hashlib.sha256).digest(),
        hmac.new(master, b"mtgc-tenant-key/mac", hashlib.sha256).digest(),
    )


def _stream(enc_key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:n])


def encrypt(plaintext: bytes, database_id: str, master: bytes) -> bytes:
    enc_key, mac_key = _subkeys(master)
    nonce = secrets.token_bytes(_NONCE)
    ct = bytes(a ^ b for a, b in zip(plaintext, _stream(enc_key, nonce, len(plaintext))))
    body = _VERSION + nonce + ct
    tag = hmac.new(mac_key, database_id.encode("ascii") + b"\0" + body, hashlib.sha256).digest()
    return body + tag


def decrypt(blob: bytes, database_id: str, master: bytes) -> bytes:
    if len(blob) < 1 + _NONCE + _TAG or blob[:1] != _VERSION:
        raise MasterKeyError("unrecognised ciphertext")
    enc_key, mac_key = _subkeys(master)
    body, tag = blob[:-_TAG], blob[-_TAG:]
    want = hmac.new(mac_key, database_id.encode("ascii") + b"\0" + body, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, want):
        raise MasterKeyError("ciphertext does not authenticate (wrong master key or wrong tenant)")
    nonce, ct = body[1:1 + _NONCE], body[1 + _NONCE:]
    return bytes(a ^ b for a, b in zip(ct, _stream(enc_key, nonce, len(ct))))
