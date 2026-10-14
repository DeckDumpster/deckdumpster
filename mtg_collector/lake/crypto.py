"""The tenant zone's cipher and key derivation (lakehouse K7).

One module for the envelope and the key schedule; the shipper, the read-back
and the eraser all import it, and nothing else in the tree seals or opens a
lake object.

    tenant-master.key (32 bytes, mode 600, backed up by hand)
         |  HKDF-SHA256(salt=SALT, info=database_id)
         v
    lake key, per tenant, derived and never stored
         |  AES-256-GCM, aad = the object's key
         v
    blob = VERSION | nonce(12) | ciphertext | tag

This is deliberately not `tenancy/keycrypt.py`.  That module encrypts a
tenant's Anthropic key under the BYO master; this one derives from a different
file named by a different variable, so the two secrets cannot be confused by
configuration and neither master opens the other's data.  The tombstones that
say a tenant's lake key may no longer be derived are in `lake/keys.py`.

The nonce is a function of the key, the aad and the plaintext (an SIV-style
construction), so sealing the same part twice yields the same bytes and a
retried PUT lands on the object it is retrying.  Equal nonces occur only for
equal plaintext under the same key and aad, which reveals nothing.

The aad is the object's key, which contains the database_id: a part copied under
another tenant's prefix, or to another path, fails to open.
"""

import base64
import hashlib
import hmac
import os
import stat

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MASTER_KEY_FILE_ENV = "MTGC_LAKE_MASTER_KEY_FILE"
MASTER_KEY_LEN = 32
KEY_LEN = 32
SALT = b"mtgc-lake-tenant-key/v1"
VERSION = b"\x01"
_NONCE = 12
_TAG = 16


class LakeCryptoError(Exception):
    """The master key is unusable or a blob does not authenticate."""


def master_key_path(env=None) -> str:
    env = os.environ if env is None else env
    path = env.get(MASTER_KEY_FILE_ENV)
    if not path:
        raise LakeCryptoError(f"no lake master key: set {MASTER_KEY_FILE_ENV}")
    return path


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(MASTER_KEY_LEN)).decode("ascii")


def load_master_key(path: str) -> bytes:
    try:
        st = os.stat(path)
    except FileNotFoundError:
        raise LakeCryptoError(f"lake master key file {path} does not exist") from None
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise LakeCryptoError(f"lake master key file {path} must be mode 600")
    try:
        key = base64.urlsafe_b64decode(open(path, encoding="ascii").read().strip())
    except Exception as exc:
        raise LakeCryptoError(f"lake master key file {path} is not urlsafe base64") from exc
    if len(key) != MASTER_KEY_LEN:
        raise LakeCryptoError(f"lake master key must decode to {MASTER_KEY_LEN} bytes")
    return key


def derive_key(master: bytes, database_id: str) -> bytes:
    if len(master) != MASTER_KEY_LEN:
        raise LakeCryptoError(f"lake master key must be {MASTER_KEY_LEN} bytes")
    if not database_id:
        raise LakeCryptoError("a lake key is derived for a database_id")
    return HKDF(
        algorithm=hashes.SHA256(), length=KEY_LEN, salt=SALT, info=database_id.encode("ascii"),
    ).derive(master)


def fingerprint(key: bytes) -> str:
    """A non-invertible identifier, safe to print and to keep beside a ticket."""
    return hashlib.sha256(b"mtgc-lake-fingerprint\0" + key).hexdigest()[:16]


def _aad(aad: str) -> bytes:
    return aad.encode("utf-8")


def seal(plaintext: bytes, key: bytes, aad: str) -> bytes:
    nonce = hmac.new(key, b"nonce\0" + _aad(aad) + b"\0" + plaintext, hashlib.sha256).digest()[:_NONCE]
    return VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, VERSION + _aad(aad))


def open_(blob: bytes, key: bytes, aad: str) -> bytes:
    if len(blob) < 1 + _NONCE + _TAG or blob[:1] != VERSION:
        raise LakeCryptoError("unrecognised lake ciphertext")
    nonce, body = blob[1:1 + _NONCE], blob[1 + _NONCE:]
    try:
        return AESGCM(key).decrypt(nonce, body, VERSION + _aad(aad))
    except InvalidTag:
        raise LakeCryptoError(
            "lake ciphertext does not authenticate (wrong key, wrong tenant, wrong path, or tampered)"
        ) from None
