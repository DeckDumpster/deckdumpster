"""The only constructor of tenant paths.

Everything under $MTGC_HOME that belongs to one tenant is named by its
database_id — an opaque, uppercase ULID — and never by its handle. A handle is
a label that can be renamed, retired and later given to somebody else; a path
built from one would let a re-created name reach the old account's data and
backups. So no function here accepts a handle, and every one that takes an id
validates it first, which also closes `../` and case-folding tricks.
"""

import os
import re
import secrets
import time
from pathlib import Path

from mtg_collector.utils import get_mtgc_home

# Crockford base32, no I L O U. A ULID's first character is at most 7 (48-bit time).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_RE = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
_HANDLE_RE = re.compile(r"[a-z][a-z0-9-]{1,30}[a-z0-9]")

REGISTRY_FILE = "registry.sqlite"
SHARED_FILE = "shared.sqlite"
TENANTS_DIR = "tenants"
TENANT_FILES_DIR = "tenant-files"


class InvalidDatabaseId(ValueError):
    pass


class InvalidHandle(ValueError):
    pass


def new_database_id() -> str:
    """A fresh ULID: 48-bit millisecond time then 80 random bits, uppercase."""
    n = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[n & 31])
        n >>= 5
    return "".join(reversed(out))


def validate_database_id(database_id: str) -> str:
    """Return `database_id` unchanged, or raise. Lowercase is refused, not folded."""
    if not isinstance(database_id, str) or not _ULID_RE.fullmatch(database_id):
        raise InvalidDatabaseId(f"not an uppercase ULID: {database_id!r}")
    return database_id


def validate_handle(handle: str) -> str:
    """Return `handle` unchanged, or raise: 3-32 chars of a-z, 0-9, '-'; starts with a letter."""
    if not isinstance(handle, str) or not _HANDLE_RE.fullmatch(handle):
        raise InvalidHandle(
            f"invalid handle {handle!r}: 3-32 characters of a-z, 0-9 and '-', "
            "starting with a letter and not ending with '-'"
        )
    return handle


def home() -> Path:
    return get_mtgc_home()


def registry_file() -> Path:
    return home() / REGISTRY_FILE


def shared_file() -> Path:
    return home() / SHARED_FILE


def tenants_dir() -> Path:
    return home() / TENANTS_DIR


def tenant_db_file(database_id: str) -> Path:
    return tenants_dir() / f"{validate_database_id(database_id)}.sqlite"


def tenant_files_dir(database_id: str) -> Path:
    return home() / TENANT_FILES_DIR / validate_database_id(database_id)


def tenant_source_dir(database_id: str) -> Path:
    return tenant_files_dir(database_id) / "source"


def tenant_ingest_dir(database_id: str) -> Path:
    return tenant_files_dir(database_id) / "ingest"


def tenant_sqlite_siblings(database_id: str) -> list[Path]:
    """The tenant file and the WAL/SHM files SQLite keeps beside it."""
    db = tenant_db_file(database_id)
    return [db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")]


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path
