"""Per-tenant image placement, filename containment, and OCR recovery targets."""

import pytest

from mtg_collector.db import registry
from mtg_collector.tenancy import images, keycrypt, paths
from mtg_collector.utils import store_source_image

A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
B = "01BX5ZZKBKACTAV9WEVGEMMVRY"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_MULTITENANT", raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    return tmp_path


def test_single_tenant_keeps_legacy_layout(home):
    assert images.ingest_images_dir(None) == home / "ingest_images"
    assert images.source_images_dir(None) == home / "source_images"


def test_tenant_dirs_are_under_tenant_files(home):
    assert images.ingest_images_dir(A) == home / "tenant-files" / A / "ingest"
    assert images.source_images_dir(B) == home / "tenant-files" / B / "source"
    assert images.ingest_images_dir(A) != images.ingest_images_dir(B)


def test_bad_tenant_id_refused(home):
    with pytest.raises(paths.InvalidDatabaseId):
        images.ingest_images_dir(A.lower())


def test_filename_cannot_leave_tenant_dir(home):
    (images.ingest_images_dir(B) / "b.jpg").write_bytes(b"b")
    (images.ingest_images_dir(A) / "a.jpg").write_bytes(b"a")
    assert images.tenant_image_path(A, "a.jpg").read_bytes() == b"a"
    # Control arm: the file exists in B, so a traversal that worked would return it.
    assert images.tenant_image_path(B, "b.jpg").is_file()
    for bad in ("", ".", "..", f"../{B}/ingest/b.jpg", f"../../{B}/ingest/b.jpg", "a/b.jpg", "x\\y"):
        assert images.tenant_image_path(A, bad) is None


def test_store_source_image_goes_to_tenant_dir(home, tmp_path):
    src = tmp_path / "x.jpg"
    src.write_bytes(b"x")
    dest = store_source_image(str(src), A)
    assert dest.startswith(str(home / "tenant-files" / A / "source"))
    assert store_source_image(str(src)).startswith(str(home / "source_images"))


def test_recovery_single_mode_is_the_one_db(home):
    assert images.recovery_targets("/x/db.sqlite") == [(None, "/x/db.sqlite")]


def test_recovery_multi_mode_loops_active_tenants_only(home, monkeypatch):
    monkeypatch.setenv("MTGC_MULTITENANT", "1")
    conn = registry.open_registry()
    a = registry.create_tenant(conn, "alice")
    b = registry.create_tenant(conn, "bobby")
    registry.detach_tenant(conn, "bobby")
    conn.close()
    assert images.recovery_targets("/x/db.sqlite") == [(a, str(paths.tenant_db_file(a)))]
    assert b not in [t for t, _ in images.recovery_targets("/x/db.sqlite")]
