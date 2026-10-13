"""Moving a pre-tenancy deployment onto a ULID tenant, and back (sp-hvjyas).

The legacy `collection.sqlite` is **never written**. Every step works on a copy,
so every step is reversible by leaving the original in place, and `rollback` is
only a detach: the legacy file is still exactly what it was and can serve again.

Each step is idempotent, refuses a database a writer holds, and is invoked by
hand (`mtg tenant legacy-migrate` / `legacy-rollback`). Nothing here is imported
by the server, so none of it can become a startup gate (D5).

Backups are not touched. The old backup prefix keeps being addressable because
this module neither copies, renames nor deletes anything under it.
"""

import hashlib
import os
import sqlite3
from contextlib import closing
from typing import Optional

from mtg_collector.db import registry
from mtg_collector.db.registry import RegistryError
from mtg_collector.tenancy import paths


class BusyError(RegistryError):
    """Another connection holds a write lock on the database."""


def refuse_if_busy(path: str) -> None:
    """Fail if a writer holds `path`. Taking and dropping the write lock is the probe."""
    conn = sqlite3.connect(path, timeout=0)
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise BusyError(f"{path} is busy ({exc}); stop the writer and retry") from exc
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def _count(path: str, table: str) -> int:
    conn = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
    with closing(conn):
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            return 0
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]


def collection_digest(db: str, shared: Optional[str] = None) -> str:
    """Hash of what the collection page reads: every `collection_view` row, in id order."""
    from mtg_collector.db.connection import open_connection

    conn = open_connection(db, shared, wal=False)
    with closing(conn):
        h = hashlib.sha256()
        for row in conn.execute("SELECT * FROM collection_view ORDER BY id"):
            h.update(repr(tuple(row)).encode())
        return h.hexdigest()


def ensure_shared(source: str, legacy_shared: Optional[str] = None) -> str:
    """Make `$MTGC_HOME/shared.sqlite` hold the catalogue. An existing one is kept, never rewritten."""
    dest = str(paths.shared_file())
    if os.path.exists(dest) and _count(dest, "printings"):
        return dest
    paths.ensure_private_dir(paths.home())
    tmp = dest + ".partial"
    try:
        if legacy_shared:
            src = sqlite3.connect(f"file:{os.path.abspath(legacy_shared)}?mode=ro", uri=True)
        elif _count(source, "printings"):
            from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, init_db

            src = sqlite3.connect(f"file:{os.path.abspath(source)}?mode=ro", uri=True)
        else:
            raise RegistryError(
                f"{source} holds no catalogue and no shared.sqlite exists; "
                "pass --legacy-shared to say where the catalogue is"
            )
        with closing(src):
            out = sqlite3.connect(tmp, uri=True)
            with closing(out):
                if legacy_shared:
                    src.backup(out)
                else:
                    # Same copy `mtg db split` makes, minus the prune: the source is not ours to edit.
                    init_db(out)
                    out.execute("ATTACH DATABASE ? AS src", (f"file:{os.path.abspath(source)}?mode=ro",))
                    for t in SHARED_TABLES + SHARED_VIEWS:
                        if out.execute(
                            "SELECT 1 FROM src.sqlite_master WHERE type='table' AND name=?", (t,)
                        ).fetchone():
                            out.execute(f"DELETE FROM main.[{t}]")
                            out.execute(f"INSERT INTO main.[{t}] SELECT * FROM src.[{t}]")
                    out.commit()
                    out.execute("DETACH DATABASE src")
                    from mtg_collector.db.schema import rebuild_fts
                    rebuild_fts(out)
                    out.commit()
        os.replace(tmp, dest)
    finally:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(tmp + suffix):
                os.unlink(tmp + suffix)
    return dest


def _prune_catalogue(tenant_file: str) -> None:
    """A tenant file holds no catalogue object (sp-y8iflb): drop what the copy carried over."""
    from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, SHARED_VIRTUAL

    conn = sqlite3.connect(tenant_file)
    with closing(conn):
        for n in SHARED_TABLES + SHARED_VIEWS + SHARED_VIRTUAL:
            row = conn.execute("SELECT type FROM sqlite_master WHERE name=?", (n,)).fetchone()
            if row and row[0] in ("table", "view"):
                conn.execute(f"DROP {row[0].upper()} IF EXISTS [{n}]")
        conn.commit()
        conn.execute("VACUUM")


def migrate_legacy(conn, handle: str, source: str, *, legacy_shared: Optional[str] = None):
    """Copy `source` onto a fresh ULID under `handle`. Returns (database_id, 'created'|'already').

    Idempotent: with an active `handle` it does nothing. After a rollback it
    makes a *new* copy of the legacy file, since the legacy file is what served
    in between; the detached tenant stays for reattach or purge.
    """
    paths.validate_handle(handle)
    try:
        return registry.find_tenant(conn, handle)["database_id"], "already"
    except RegistryError:
        pass
    refuse_if_busy(source)
    shared = ensure_shared(source, legacy_shared)
    want = collection_digest(source, legacy_shared if legacy_shared else None)

    database_id = registry.adopt_database(conn, handle, source)
    try:
        dest = str(paths.tenant_db_file(database_id))
        _prune_catalogue(dest)
        registry.migrate_tenant(database_id)
        got = collection_digest(dest, shared)
        if got != want:
            raise RegistryError(f"served collection differs after migration ({want[:12]} != {got[:12]})")
    except BaseException:
        registry.detach_tenant(conn, handle)
        registry.purge_tenant(conn, handle)
        raise
    return database_id, "created"


def rollback_legacy(conn, handle: str):
    """Detach the tenant so the legacy file serves again. Returns (database_id, 'detached'|'already')."""
    try:
        row = registry.find_tenant(conn, handle)
    except RegistryError:
        return registry.find_detached(conn, handle)["database_id"], "already"
    tenant_file = paths.tenant_db_file(row["database_id"])
    if tenant_file.exists():
        refuse_if_busy(str(tenant_file))
    return registry.detach_tenant(conn, handle), "detached"
