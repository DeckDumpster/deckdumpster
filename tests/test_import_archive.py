"""`mtg tenant import-archive` (sp-uoenuj): a hand-built archive through a scratch multi-tenant home.

The archive is built here to the documented format, not by the export script.
"""

import hashlib
import io
import json
import sqlite3
import tarfile

import pytest

from mtg_collector.db import registry
from mtg_collector.tenancy import archive, images, keycrypt, paths

SRC_HOME = "/home/friend/.mtgc"
FILES = {
    "images/ingest_images/a.jpg": b"ingest-bytes",
    "images/source_images/b_1234.jpg": b"source-bytes",
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("MTGC_HOME", str(h))
    monkeypatch.delenv("MTGC_DB", raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    return h


def _db(path, source_image):
    from mtg_collector.db.schema import init_db, rebuild_fts, refresh_latest_prices

    c = sqlite3.connect(path)
    init_db(c)
    c.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test')")
    c.execute("INSERT INTO cards (oracle_id, name, type_line) VALUES ('o1', 'Alpha', 'Instant')")
    c.execute("INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
              "VALUES ('p1', 'o1', 'tst', '1', 'R')")
    refresh_latest_prices(c)
    rebuild_fts(c)
    c.execute("INSERT INTO collection (printing_id, finish, condition, status, acquired_at, source, source_image, card_name) "
              "VALUES ('p1', 'nonfoil', 'Near Mint', 'owned', '2025-01-01T00:00:00.000Z', 'test', ?, 'Alpha')",
              (source_image,))
    c.execute("INSERT INTO ingest_images (filename, stored_name, md5, status, created_at, updated_at) "
              "VALUES ('a.jpg', 'a.jpg', 'x', 'DONE', 'n', 'n')")
    c.execute("INSERT INTO ingest_lineage (collection_id, image_md5, image_path, card_index, created_at) "
              "VALUES (1, 'x', ?, 0, 'n')", (f"{SRC_HOME}/ingest_images/a.jpg",))
    c.commit()
    c.close()


def _counts(path):
    c = sqlite3.connect(path)
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    out = {n: c.execute(f"SELECT COUNT(*) FROM [{n}]").fetchone()[0] for n in names}
    c.close()
    return out


def _build(tmp_path, *, tamper=False, stray_path=None):
    work = tmp_path / "build"
    work.mkdir()
    db = str(work / "collection.sqlite")
    _db(db, stray_path or f"{SRC_HOME}/source_images/b_1234.jpg")
    manifest = {
        "format": 1, "exported_at": "2026-10-20T00:00:00Z", "mtgc_home": SRC_HOME,
        "schema_version": 1, "commit": None, "row_counts": _counts(db),
        "files": [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in FILES.items()],
    }
    out = tmp_path / "deckdumpster-export-host-20261020T000000Z.tar.gz"
    with tarfile.open(out, "w:gz") as tf:
        def add(name, data):
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        add("manifest.json", json.dumps(manifest).encode())
        add("collection.sqlite", open(db, "rb").read())
        for p, b in FILES.items():
            add(p, b + b"!" if tamper and p.endswith("a.jpg") else b)
    return str(out)


def _tenants():
    c = registry.open_registry()
    try:
        return [r["handle"] for r in registry.list_tenants(c)]
    finally:
        c.close()


def test_import_serves_images_from_the_tenant_directory(home, tmp_path):
    # the shared catalogue is the archive's own (a fresh install has none yet)
    out = archive.import_archive(_build(tmp_path), "friend", "Friend@Example.com")
    dbid = out
    c = sqlite3.connect(paths.tenant_db_file(dbid))
    (src,) = c.execute("SELECT source_image FROM collection").fetchone()
    (lin,) = c.execute("SELECT image_path FROM ingest_lineage").fetchone()
    (stored,) = c.execute("SELECT stored_name FROM ingest_images").fetchone()
    c.close()
    assert src == str(paths.tenant_source_dir(dbid) / "b_1234.jpg")
    assert lin == str(paths.tenant_ingest_dir(dbid) / "a.jpg")
    assert open(src, "rb").read() == FILES["images/source_images/b_1234.jpg"]
    assert images.tenant_image_path(dbid, stored).read_bytes() == FILES["images/ingest_images/a.jpg"]
    r = registry.open_registry()
    assert registry.resolve_identity(r, "friend@example.com") == "friend"
    r.close()


def test_a_tampered_file_fails_the_hash_check_and_creates_nothing(home, tmp_path):
    with pytest.raises(archive.ArchiveError, match="hash check"):
        archive.import_archive(_build(tmp_path, tamper=True), "friend", "f@example.com")
    assert _tenants() == []


def test_a_path_naming_a_file_not_in_the_archive_is_refused(home, tmp_path):
    with pytest.raises(archive.ArchiveError, match="not in the archive"):
        archive.import_archive(
            _build(tmp_path, stray_path=f"{SRC_HOME}/source_images/missing.jpg"), "friend", "f@example.com")
    assert _tenants() == []


def test_dry_run_leaves_production_untouched(home, tmp_path):
    before = sorted(p.name for p in home.rglob("*"))
    archive.import_archive(_build(tmp_path), "friend", "f@example.com", dry_run=True)
    assert _tenants() == []
    assert not (home / "tenant-files").exists()
    assert [n for n in sorted(p.name for p in home.rglob("*")) if not n.startswith("registry")] == \
        [n for n in before if not n.startswith("registry")]
