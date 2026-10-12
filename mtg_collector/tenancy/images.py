"""Where a tenant's photos live, and which tenants have work to recover.

`tenant_id` is a database_id, or None for single-tenant mode (the default),
which keeps the pre-tenancy layout — `$MTGC_HOME/ingest_images` and
`source_images` — so one person's install is untouched until multi-tenancy is
switched on. With an id, everything lands under `tenant-files/<id>/` and the
directory is the isolation: no function here takes a path from a request, and
a filename is a single validated component resolved inside one tenant's dir.
"""

import os
import re
from pathlib import Path
from typing import Optional

from mtg_collector.tenancy import paths
from mtg_collector.utils import get_mtgc_home

_FILENAME_RE = re.compile(r"[^/\\\x00]+")


def ingest_images_dir(tenant_id: Optional[str]) -> Path:
    if tenant_id is None:
        d = get_mtgc_home() / "ingest_images"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return paths.ensure_private_dir(_ensure_parents(paths.tenant_ingest_dir(tenant_id)))


def source_images_dir(tenant_id: Optional[str]) -> Path:
    if tenant_id is None:
        d = get_mtgc_home() / "source_images"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return paths.ensure_private_dir(_ensure_parents(paths.tenant_source_dir(tenant_id)))


def _ensure_parents(d: Path) -> Path:
    paths.ensure_private_dir(d.parent)
    return d


def tenant_image_path(tenant_id: Optional[str], filename: str) -> Optional[Path]:
    """The file `filename` names inside the tenant's ingest dir, or None.

    None for anything that is not one plain path component, so `../` and
    another tenant's directory are unreachable by construction.
    """
    if filename in ("", ".", "..") or not _FILENAME_RE.fullmatch(filename):
        return None
    base = ingest_images_dir(tenant_id)
    path = base / filename
    if path.resolve().parent != base.resolve():
        return None
    return path


def multitenant_enabled() -> bool:
    return bool(os.environ.get("MTGC_MULTITENANT"))


def recovery_targets(single_db_path: str) -> list[tuple[Optional[str], str]]:
    """(tenant_id, db_path) for every database whose pending OCR must be recovered.

    Single-tenant mode: the one configured database, tenant None. Multi mode:
    every active tenant in the registry — a detached or purged one has no
    business consuming OCR — and never the single path.
    """
    if not multitenant_enabled():
        return [(None, single_db_path)]
    from mtg_collector.db import registry

    conn = registry.open_registry(create=False)
    try:
        rows = registry.list_tenants(conn)
    finally:
        conn.close()
    return [
        (r["database_id"], str(paths.tenant_db_file(r["database_id"])))
        for r in rows
        if registry.state(r) == "active"
    ]
