"""The control plane: which tenants exist, who may reach them, and their secrets.

`registry.sqlite` holds three tables and no tenant data. `user` maps a handle —
a human label, reusable once retired — to an opaque `database_id`, and the
database_id is the only thing any path is ever built from (see
`mtg_collector.tenancy.paths`). `user_identity` binds a verified email to one
database_id. `tenant_key` holds a tenant's encrypted secret.

Rules live in the schema as CHECKs and partial unique indexes, not only in the
functions below, so a hand-written INSERT cannot break them.

Lifecycle: create -> active; detach -> retired (files stay, nobody can reach
them); reattach -> active again; purge -> files and key gone, row kept. A purged
row is never deleted: its database_id stays spent, and the handle may be given
to a new tenant with a new database_id and so a new set of files.
"""

import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from mtg_collector.tenancy import keycrypt, paths
from mtg_collector.utils import now_iso

REGISTRY_VERSION = 1

REGISTRY_SQL = """
CREATE TABLE IF NOT EXISTS user (
    database_id TEXT PRIMARY KEY
        CHECK (length(database_id) = 26
               AND database_id NOT GLOB '*[^0-9A-HJKMNP-TV-Z]*'
               AND substr(database_id, 1, 1) <= '7'),
    handle      TEXT NOT NULL
        CHECK (length(handle) BETWEEN 3 AND 32
               AND handle GLOB '[a-z]*'
               AND handle NOT GLOB '*[^a-z0-9-]*'
               AND handle NOT GLOB '*-'),
    created_at  TEXT NOT NULL,
    retired_at  TEXT,
    purged_at   TEXT,
    CHECK (purged_at IS NULL OR retired_at IS NOT NULL)
);

-- One active tenant per handle; retired and purged rows keep theirs, unclaimed.
CREATE UNIQUE INDEX IF NOT EXISTS user_active_handle
    ON user(handle) WHERE retired_at IS NULL;

CREATE TABLE IF NOT EXISTS user_identity (
    email       TEXT NOT NULL
        CHECK (email = lower(email) AND email = trim(email)
               AND email LIKE '_%@_%.%' AND email NOT LIKE '% %'),
    database_id TEXT NOT NULL REFERENCES user(database_id),
    created_at  TEXT NOT NULL,
    retired_at  TEXT
);

-- One active tenant per email.
CREATE UNIQUE INDEX IF NOT EXISTS user_identity_active_email
    ON user_identity(email) WHERE retired_at IS NULL;
CREATE INDEX IF NOT EXISTS user_identity_database_id ON user_identity(database_id);

CREATE TABLE IF NOT EXISTS tenant_key (
    database_id TEXT PRIMARY KEY REFERENCES user(database_id),
    ciphertext  BLOB NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class RegistryError(Exception):
    """A registry rule refused the operation."""


class RegistryTooNewError(RegistryError):
    """registry.sqlite was written by newer code than this process runs."""


def open_registry(path=None, *, create: bool = True) -> sqlite3.Connection:
    path = str(path or paths.registry_file())
    if not create and not os.path.exists(path):
        raise RegistryError(f"no registry at {path}")
    paths.ensure_private_dir(Path(path).parent)
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    found = conn.execute("PRAGMA user_version").fetchone()[0]
    if found > REGISTRY_VERSION:
        conn.close()
        raise RegistryTooNewError(
            f"registry records version {found}, this code understands up to "
            f"{REGISTRY_VERSION}; refusing to open it"
        )
    if found < REGISTRY_VERSION:
        conn.executescript(REGISTRY_SQL)
        conn.execute(f"PRAGMA user_version = {REGISTRY_VERSION}")
    return conn


class _tx:
    """BEGIN IMMEDIATE ... COMMIT, turning constraint failures into RegistryError."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
            return False
        self.conn.execute("ROLLBACK")
        if issubclass(exc_type, sqlite3.IntegrityError):
            raise RegistryError(f"registry rule refused it: {exc}") from exc
        return False


def find_tenant(conn, handle: str, *, active_only: bool = True):
    """The tenant row a handle names: the active one, else the latest retired one."""
    paths.validate_handle(handle)
    row = conn.execute(
        "SELECT * FROM user WHERE handle = ? AND retired_at IS NULL", (handle,)
    ).fetchone()
    if row or active_only:
        if not row:
            raise RegistryError(f"no active tenant with handle {handle!r}")
        return row
    row = conn.execute(
        "SELECT * FROM user WHERE handle = ? AND purged_at IS NULL "
        "ORDER BY retired_at DESC LIMIT 1", (handle,)
    ).fetchone()
    if not row:
        raise RegistryError(f"no detached tenant with handle {handle!r}")
    return row


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def state(row) -> str:
    if row["purged_at"]:
        return "purged"
    return "detached" if row["retired_at"] else "active"


def list_tenants(conn):
    return conn.execute(
        "SELECT u.*, (SELECT count(*) FROM user_identity i "
        "             WHERE i.database_id = u.database_id AND i.retired_at IS NULL) AS identities, "
        "       EXISTS (SELECT 1 FROM tenant_key k WHERE k.database_id = u.database_id) AS has_key "
        "FROM user u ORDER BY u.created_at, u.database_id"
    ).fetchall()


def create_tenant(conn, handle: str, *, init_files: bool = True) -> str:
    """Register a new tenant and create its empty database. Returns its database_id."""
    paths.validate_handle(handle)
    database_id = paths.new_database_id()
    db_file = paths.tenant_db_file(database_id)
    paths.ensure_private_dir(db_file.parent)
    with _tx(conn):
        conn.execute(
            "INSERT INTO user (database_id, handle, created_at) VALUES (?, ?, ?)",
            (database_id, handle, now_iso()),
        )
        if init_files:
            try:
                _init_tenant_file(database_id)
            except BaseException:
                for f in paths.tenant_sqlite_siblings(database_id):
                    f.unlink(missing_ok=True)
                raise
    return database_id


def _init_tenant_file(database_id: str) -> None:
    from mtg_collector.db.connection import open_connection
    from mtg_collector.db.schema import init_db

    shared = paths.shared_file()
    conn = open_connection(str(paths.tenant_db_file(database_id)), str(shared))
    with closing(conn):
        init_db(conn)
        conn.commit()


def rename_tenant(conn, handle: str, new_handle: str) -> None:
    paths.validate_handle(new_handle)
    row = find_tenant(conn, handle)
    with _tx(conn):
        conn.execute(
            "UPDATE user SET handle = ? WHERE database_id = ?", (new_handle, row["database_id"])
        )


def detach_tenant(conn, handle: str) -> str:
    """Make the tenant unreachable. Files stay; identities are retired with it."""
    row = find_tenant(conn, handle)
    ts = now_iso()
    with _tx(conn):
        conn.execute("UPDATE user SET retired_at = ? WHERE database_id = ?", (ts, row["database_id"]))
        conn.execute(
            "UPDATE user_identity SET retired_at = ? WHERE database_id = ? AND retired_at IS NULL",
            (ts, row["database_id"]),
        )
    return row["database_id"]


def reattach_tenant(conn, handle: str, *, as_handle: Optional[str] = None) -> str:
    """Bring a detached tenant back, with the identities that went with it."""
    row = find_tenant(conn, handle, active_only=False)
    if row["retired_at"] is None:
        raise RegistryError(f"tenant {handle!r} is not detached")
    new_handle = as_handle or handle
    paths.validate_handle(new_handle)
    if not paths.tenant_db_file(row["database_id"]).exists():
        raise RegistryError(f"tenant {row['database_id']} has no database file to reattach")
    with _tx(conn):
        conn.execute(
            "UPDATE user SET retired_at = NULL, handle = ? WHERE database_id = ?",
            (new_handle, row["database_id"]),
        )
        conn.execute(
            "UPDATE user_identity SET retired_at = NULL "
            "WHERE database_id = ? AND retired_at = ?",
            (row["database_id"], row["retired_at"]),
        )
    return row["database_id"]


def purge_tenant(conn, handle: str) -> str:
    """Delete a detached tenant's files and key. The registry row stays, spent."""
    row = find_tenant(conn, handle, active_only=False)
    if row["retired_at"] is None:
        raise RegistryError(f"tenant {handle!r} is active; detach it before purging")
    database_id = row["database_id"]
    with _tx(conn):
        conn.execute("UPDATE user SET purged_at = ? WHERE database_id = ?", (now_iso(), database_id))
        conn.execute("DELETE FROM tenant_key WHERE database_id = ?", (database_id,))
        for f in paths.tenant_sqlite_siblings(database_id):
            f.unlink(missing_ok=True)
        files = paths.tenant_files_dir(database_id)
        if files.exists():
            shutil.rmtree(files)
    return database_id


def adopt_database(conn, handle: str, source: str) -> str:
    """Register an existing database file as a new tenant. The source is copied, not moved."""
    from mtg_collector.db.connection import file_schema_version, refuse_if_newer

    paths.validate_handle(handle)
    if not os.path.isfile(source):
        raise RegistryError(f"no such database: {source}")
    database_id = paths.new_database_id()
    dest = paths.tenant_db_file(database_id)
    paths.ensure_private_dir(dest.parent)
    with _tx(conn):
        conn.execute(
            "INSERT INTO user (database_id, handle, created_at) VALUES (?, ?, ?)",
            (database_id, handle, now_iso()),
        )
        try:
            src = sqlite3.connect("file:" + os.path.abspath(source) + "?mode=ro", uri=True)
            with closing(src):
                if src.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RegistryError(f"{source} fails PRAGMA quick_check")
                if file_schema_version(src) == 0:
                    raise RegistryError(f"{source} has no schema_version; not an mtgc database")
                refuse_if_newer(src)
                out = sqlite3.connect(str(dest))
                with closing(out):
                    src.backup(out)
        except BaseException:
            for f in paths.tenant_sqlite_siblings(database_id):
                f.unlink(missing_ok=True)
            raise
    return database_id


def migrate_tenant(database_id: str) -> tuple[int, int]:
    """Bring one tenant file to the current schema. Returns (before, after)."""
    from mtg_collector.db.connection import file_schema_version, open_connection
    from mtg_collector.db.schema import init_db

    conn = open_connection(str(paths.tenant_db_file(database_id)), str(paths.shared_file()))
    with closing(conn):
        before = file_schema_version(conn)
        init_db(conn)
        conn.commit()
        return before, file_schema_version(conn)


def add_identity(conn, handle: str, email: str) -> None:
    email = _normalise_email(email)
    row = find_tenant(conn, handle)
    with _tx(conn):
        conn.execute(
            "INSERT INTO user_identity (email, database_id, created_at) VALUES (?, ?, ?)",
            (email, row["database_id"], now_iso()),
        )


def remove_identity(conn, email: str) -> None:
    email = _normalise_email(email)
    with _tx(conn):
        n = conn.execute(
            "UPDATE user_identity SET retired_at = ? WHERE email = ? AND retired_at IS NULL",
            (now_iso(), email),
        ).rowcount
        if n == 0:
            raise RegistryError(f"no active identity {email!r}")


def list_identities(conn, handle: Optional[str] = None):
    sql = (
        "SELECT i.email, u.handle, i.database_id, i.created_at "
        "FROM user_identity i JOIN user u USING (database_id) "
        "WHERE i.retired_at IS NULL AND u.retired_at IS NULL"
    )
    args: tuple = ()
    if handle:
        sql += " AND u.handle = ?"
        args = (handle,)
    return conn.execute(sql + " ORDER BY i.email", args).fetchall()


def resolve_identity(conn, email: str) -> Optional[str]:
    """The database_id an email is bound to, or None. Never creates anything."""
    row = conn.execute(
        "SELECT i.database_id FROM user_identity i JOIN user u USING (database_id) "
        "WHERE i.email = ? AND i.retired_at IS NULL AND u.retired_at IS NULL",
        (_normalise_email(email),),
    ).fetchone()
    return row[0] if row else None


def set_tenant_key(conn, handle: str, secret: str) -> None:
    row = find_tenant(conn, handle)
    blob = keycrypt.encrypt(secret.encode("utf-8"), row["database_id"], keycrypt.master_key())
    with _tx(conn):
        conn.execute(
            "INSERT INTO tenant_key (database_id, ciphertext, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(database_id) DO UPDATE SET ciphertext = excluded.ciphertext, "
            "updated_at = excluded.updated_at",
            (row["database_id"], blob, now_iso()),
        )


def get_tenant_key(conn, database_id: str) -> Optional[str]:
    paths.validate_database_id(database_id)
    row = conn.execute(
        "SELECT ciphertext FROM tenant_key k JOIN user u USING (database_id) "
        "WHERE k.database_id = ? AND u.retired_at IS NULL", (database_id,)
    ).fetchone()
    if not row:
        return None
    return keycrypt.decrypt(row[0], database_id, keycrypt.master_key()).decode("utf-8")
