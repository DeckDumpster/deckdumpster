"""Importing an export-install archive as a new tenant (sp-uoenuj).

The archive is one `deckdumpster-export-<host>-<UTC>.tar.gz` holding
`manifest.json`, `collection.sqlite` and `images/{ingest_images,source_images}/`.
The database goes through `upgrade.migrate_legacy` (never writes its source,
refuses a busy file, checks space, compares `collection_digest`); this module
adds the manifest and hash checks, the image copy, the rewrite of stored
absolute paths, and the final count comparison. Nothing outside the new tenant
is touched; a failure after the tenant exists detaches and purges it.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Callable

from mtg_collector.db import registry
from mtg_collector.db.registry import RegistryError
from mtg_collector.db.schema import SHARED_TABLES, SHARED_VIEWS, SHARED_VIRTUAL
from mtg_collector.tenancy import paths, upgrade

FORMAT = 1
IMAGE_DIRS = ("ingest_images", "source_images")
# (table, column) pairs that hold an absolute path under the source's $MTGC_HOME
PATH_COLUMNS = (
    ("collection", "source_image"),
    ("ingest_cache", "image_path"),
    ("ingest_lineage", "image_path"),
)


class ArchiveError(RegistryError):
    pass


def _nothing(_line: str) -> None:
    pass


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(archive: str, dest: Path) -> dict:
    """Unpack `archive` into the empty `dest`, regular files only, and return the verified manifest."""
    try:
        tf = tarfile.open(archive, "r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise ArchiveError(f"{archive} is not a readable .tar.gz: {exc}") from exc
    with tf:
        root = dest.resolve()
        for m in tf:
            if m.isdir():
                continue
            parts = Path(m.name).parts
            if not m.isreg() or Path(m.name).is_absolute() or ".." in parts:
                raise ArchiveError(f"archive member {m.name!r} is not a plain relative file")
            target = (root / m.name).resolve()
            if root not in target.parents:
                raise ArchiveError(f"archive member {m.name!r} escapes the archive")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return verify(dest)


def verify(root: Path) -> dict:
    mpath = root / "manifest.json"
    if not mpath.is_file():
        raise ArchiveError("archive has no manifest.json")
    manifest = json.loads(mpath.read_text())
    if manifest.get("format") != FORMAT:
        raise ArchiveError(f"manifest format {manifest.get('format')!r}, this importer reads {FORMAT}")
    for key in ("mtgc_home", "schema_version", "row_counts", "files"):
        if key not in manifest:
            raise ArchiveError(f"manifest has no {key!r}")
    if not (root / "collection.sqlite").is_file():
        raise ArchiveError("archive has no collection.sqlite")
    listed = set()
    for f in manifest["files"]:
        rel = f["path"]
        listed.add(rel)
        parts = Path(rel).parts
        if len(parts) < 3 or parts[0] != "images" or parts[1] not in IMAGE_DIRS or ".." in parts:
            raise ArchiveError(f"manifest lists {rel!r}, outside images/{{{','.join(IMAGE_DIRS)}}}/")
        p = root / rel
        if not p.is_file():
            raise ArchiveError(f"manifest lists {rel} but the archive does not hold it")
        if p.stat().st_size != f["size"] or _sha256(p) != f["sha256"]:
            raise ArchiveError(f"{rel} fails its manifest hash check; the archive was altered or damaged")
    on_disk = {
        p.relative_to(root).as_posix() for p in (root / "images").rglob("*") if p.is_file()
    } if (root / "images").is_dir() else set()
    extra = on_disk - listed
    if extra:
        raise ArchiveError(f"archive holds files the manifest does not list: {sorted(extra)[:3]}")
    return manifest


def _plan_rewrites(db: str, mtgc_home: str, listed: set) -> dict:
    """{(table, column): [(old, relative image path)]} for every stored path under mtgc_home.

    Refuses a path that names a file the archive does not hold, or a place
    under mtgc_home that is not one of the two image directories.
    """
    prefix = mtgc_home.rstrip("/") + "/"
    plan = {}
    conn = sqlite3.connect(f"file:{os.path.abspath(db)}?mode=ro", uri=True)
    with closing(conn):
        for table, col in PATH_COLUMNS:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            olds = [r[0] for r in conn.execute(
                f"SELECT DISTINCT [{col}] FROM [{table}] WHERE [{col}] LIKE ? ESCAPE '\\'",
                (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",))]
            for old in olds:
                rel = "images/" + old[len(prefix):]
                if old[len(prefix):].split("/", 1)[0] not in IMAGE_DIRS:
                    raise ArchiveError(f"{table}.{col} names {old}, which is not under {prefix}{{{','.join(IMAGE_DIRS)}}}")
                if rel not in listed:
                    raise ArchiveError(f"{table}.{col} names {old}, which is not in the archive")
                plan.setdefault((table, col), []).append((old, rel))
    return plan


def _tenant_dir(database_id: str, image_dir: str) -> Path:
    return (paths.tenant_ingest_dir if image_dir == "ingest_images" else paths.tenant_source_dir)(database_id)


def _copy_images(root: Path, manifest: dict, database_id: str) -> int:
    n = 0
    for f in manifest["files"]:
        _, image_dir, *rest = Path(f["path"]).parts
        dest_dir = paths.ensure_private_dir(_tenant_dir(database_id, image_dir))
        dest = dest_dir.joinpath(*rest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / f["path"], dest)
        n += 1
    return n


def _rewrite(db: str, plan: dict, database_id: str, mtgc_home: str) -> int:
    prefix = mtgc_home.rstrip("/") + "/"
    changed = 0
    conn = sqlite3.connect(db)
    with closing(conn):
        for (table, col), items in plan.items():
            for old, _rel in items:
                image_dir, *rest = old[len(prefix):].split("/")
                new = str(_tenant_dir(database_id, image_dir).joinpath(*rest))
                changed += conn.execute(f"UPDATE [{table}] SET [{col}] = ? WHERE [{col}] = ?", (new, old)).rowcount
        conn.commit()
    return changed


def _tenant_counts(db: str, tables) -> dict:
    conn = sqlite3.connect(f"file:{os.path.abspath(db)}?mode=ro", uri=True)
    with closing(conn):
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] if t in have else None for t in tables}


def _check_counts(db: str, manifest: dict) -> dict:
    # Catalogue objects (cards_fts and its FTS5 shadow tables, latest_prices) are not in a tenant file.
    shared = set(SHARED_TABLES) | set(SHARED_VIEWS) | set(SHARED_VIRTUAL)
    wanted = {t: n for t, n in manifest["row_counts"].items()
              if t not in shared and not t.startswith(tuple(v + "_" for v in SHARED_VIRTUAL))}
    got = _tenant_counts(db, wanted)
    bad = {t: (wanted[t], got[t]) for t in wanted if got[t] != wanted[t]}
    if bad:
        raise ArchiveError("row counts differ from the manifest (manifest, tenant): " + ", ".join(
            f"{t} {a} != {b}" for t, (a, b) in sorted(bad.items())))
    return got


def _do_import(archive, handle, email, scratch, report):
    root = scratch / "archive"
    root.mkdir()
    manifest = extract(archive, root)
    report(f"manifest ok: format {manifest['format']}, schema {manifest['schema_version']}, "
           f"{len(manifest['files'])} image files, every sha256 matches")
    db = str(root / "collection.sqlite")
    listed = {f["path"] for f in manifest["files"]}
    plan = _plan_rewrites(db, manifest["mtgc_home"], listed)

    paths.validate_handle(handle)
    email = email.strip().lower()
    with closing(registry.open_registry()) as conn:
        if registry.resolve_identity(conn, email) is not None:
            raise ArchiveError(f"{email} is already bound to a tenant")
        database_id, outcome = upgrade.migrate_legacy(conn, handle, db, report=report)
        if outcome != "created":
            raise ArchiveError(f"tenant {handle} already exists; pick a new handle")
        try:
            tenant_db = str(paths.tenant_db_file(database_id))
            images = _copy_images(root, manifest, database_id)
            rewritten = _rewrite(tenant_db, plan, database_id, manifest["mtgc_home"])
            counts = _check_counts(tenant_db, manifest)
            held = sum(1 for d in IMAGE_DIRS for p in _tenant_dir(database_id, d).rglob("*") if p.is_file())
            if images != len(manifest["files"]) or held != len(manifest["files"]):
                raise ArchiveError(f"image count {held} != manifest {len(manifest['files'])}")
            registry.add_identity(conn, handle, email)
        except BaseException:
            registry.detach_tenant(conn, handle)
            registry.purge_tenant(conn, handle)
            raise
    report(f"paths rewritten: {rewritten}")
    report(f"images: {held} of {len(manifest['files'])}")
    for t, n in sorted(counts.items()):
        report(f"rows {t}: {n} (manifest {manifest['row_counts'][t]})")
    return database_id


def import_archive(archive: str, handle: str, email: str, *, dry_run: bool = False,
                   report: Callable[[str], None] = _nothing) -> str:
    """Import `archive` as tenant `handle` bound to `email`. Returns the new database_id.

    Dry-run does the same against a scratch home holding a copy of the registry
    and a link to the shared catalogue, and removes it afterwards.
    """
    real_home = paths.home()
    paths.ensure_private_dir(real_home)
    scratch = Path(tempfile.mkdtemp(prefix="import-archive-", dir=real_home if not dry_run else None))
    saved = os.environ.get("MTGC_HOME")
    try:
        if dry_run:
            os.environ["MTGC_HOME"] = str(scratch / "home")
            (scratch / "home").mkdir()
            reg = real_home / paths.REGISTRY_FILE
            if reg.exists():
                src = sqlite3.connect(f"file:{reg}?mode=ro", uri=True)
                with closing(src), closing(sqlite3.connect(scratch / "home" / paths.REGISTRY_FILE)) as out:
                    src.backup(out)
            shared = real_home / paths.SHARED_FILE
            if shared.exists() and shared.stat().st_size > 0:
                os.symlink(shared, scratch / "home" / paths.SHARED_FILE)
            report(f"dry run against scratch home {scratch / 'home'}")
        return _do_import(archive, handle, email, scratch, report)
    finally:
        if saved is None:
            os.environ.pop("MTGC_HOME", None)
        else:
            os.environ["MTGC_HOME"] = saved
        shutil.rmtree(scratch, ignore_errors=True)
