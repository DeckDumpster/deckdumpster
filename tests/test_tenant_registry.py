"""Registry rules, path validators, tenant key custody, and the `mtg tenant` CLI."""

import os
import sqlite3
import subprocess
import sys

import pytest

from mtg_collector.db import registry
from mtg_collector.tenancy import keycrypt, paths

ULID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_DB", raising=False)
    monkeypatch.delenv("MTGC_SHARED_DB", raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    monkeypatch.delenv("MTGC_MASTER_KEY_FILE", raising=False)
    return tmp_path


@pytest.fixture
def reg(home):
    conn = registry.open_registry()
    yield conn
    conn.close()


# --- paths ---------------------------------------------------------------

def test_database_id_must_be_uppercase_ulid():
    assert paths.validate_database_id(ULID) == ULID
    for bad in (ULID.lower(), ULID[:-1], ULID + "A", "../" + ULID, "", "8" + ULID[1:], ULID.replace("A", "U")):
        with pytest.raises(paths.InvalidDatabaseId):
            paths.validate_database_id(bad)


def test_new_database_ids_validate_and_differ():
    ids = {paths.new_database_id() for _ in range(50)}
    assert len(ids) == 50
    for i in ids:
        paths.validate_database_id(i)


def test_tenant_paths_refuse_handles_and_traversal(home):
    assert paths.tenant_db_file(ULID) == home / "tenants" / f"{ULID}.sqlite"
    assert paths.tenant_files_dir(ULID) == home / "tenant-files" / ULID
    for f in (paths.tenant_db_file, paths.tenant_files_dir, paths.tenant_source_dir):
        with pytest.raises(paths.InvalidDatabaseId):
            f("alice")
        with pytest.raises(paths.InvalidDatabaseId):
            f("../../etc")


@pytest.mark.parametrize("handle", ["alice", "bob-2", "a1b"])
def test_good_handles(handle):
    assert paths.validate_handle(handle) == handle


@pytest.mark.parametrize("handle", ["", "ab", "Alice", "1abc", "al ice", "alice-", "a/b", "x" * 33, "a_b"])
def test_bad_handles(handle):
    with pytest.raises(paths.InvalidHandle):
        paths.validate_handle(handle)


# --- registry rules ------------------------------------------------------

def test_handle_check_is_in_the_schema(reg):
    for bad in ("Alice", "ab", "a_b", "alice-", "1abc"):
        with pytest.raises(sqlite3.IntegrityError):
            reg.execute("INSERT INTO user VALUES (?, ?, 'now', NULL, NULL)", (ULID, bad))


def test_database_id_check_is_in_the_schema(reg):
    with pytest.raises(sqlite3.IntegrityError):
        reg.execute("INSERT INTO user VALUES (?, 'alice', 'now', NULL, NULL)", (ULID.lower(),))


def test_one_active_handle(reg):
    registry.create_tenant(reg, "alice")
    with pytest.raises(registry.RegistryError):
        registry.create_tenant(reg, "alice")


def test_one_active_tenant_per_email(reg):
    registry.create_tenant(reg, "alice")
    registry.create_tenant(reg, "bob")
    registry.add_identity(reg, "alice", "A@Example.com")
    with pytest.raises(registry.RegistryError):
        registry.add_identity(reg, "bob", "a@example.com")
    assert registry.resolve_identity(reg, " a@EXAMPLE.com ") is not None


def test_purged_requires_detached_in_schema(reg):
    i = registry.create_tenant(reg, "alice")
    with pytest.raises(sqlite3.IntegrityError):
        reg.execute("UPDATE user SET purged_at = 'now' WHERE database_id = ?", (i,))


def test_purge_only_detached(reg, home):
    i = registry.create_tenant(reg, "alice")
    with pytest.raises(registry.RegistryError, match="detach"):
        registry.purge_tenant(reg, "alice")
    assert paths.tenant_db_file(i).exists()
    registry.detach_tenant(reg, "alice")
    registry.purge_tenant(reg, "alice")
    assert not paths.tenant_db_file(i).exists()
    row = reg.execute("SELECT * FROM user WHERE database_id = ?", (i,)).fetchone()
    assert registry.state(row) == "purged"


def test_create_makes_a_current_schema_file(reg):
    i = registry.create_tenant(reg, "alice")
    from mtg_collector.db.schema import SCHEMA_VERSION
    c = sqlite3.connect(paths.tenant_db_file(i))
    assert c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION


def test_detach_blocks_resolution_and_reattach_restores(reg):
    i = registry.create_tenant(reg, "alice")
    registry.add_identity(reg, "alice", "a@example.com")
    registry.detach_tenant(reg, "alice")
    assert registry.resolve_identity(reg, "a@example.com") is None
    registry.reattach_tenant(reg, "alice")
    assert registry.resolve_identity(reg, "a@example.com") == i


def test_recreated_handle_gets_new_id_and_files(reg):
    old = registry.create_tenant(reg, "alice")
    registry.add_identity(reg, "alice", "a@example.com")
    registry.detach_tenant(reg, "alice")
    new = registry.create_tenant(reg, "alice")
    assert new != old
    assert paths.tenant_db_file(new) != paths.tenant_db_file(old)
    # the old identity binding did not carry over to the new tenant
    assert registry.resolve_identity(reg, "a@example.com") is None
    # reattaching the old one now collides with the live handle unless renamed
    with pytest.raises(registry.RegistryError):
        registry.reattach_tenant(reg, "alice")
    assert registry.reattach_tenant(reg, "alice", as_handle="alice-old") == old


def test_reattach_refuses_when_email_rebound(reg):
    registry.create_tenant(reg, "alice")
    registry.add_identity(reg, "alice", "a@example.com")
    registry.detach_tenant(reg, "alice")
    registry.create_tenant(reg, "alice2")
    registry.add_identity(reg, "alice2", "a@example.com")
    with pytest.raises(registry.RegistryError):
        registry.reattach_tenant(reg, "alice")
    assert registry.state(reg.execute("SELECT * FROM user WHERE handle='alice'").fetchone()) == "detached"


def test_rename(reg):
    i = registry.create_tenant(reg, "alice")
    registry.rename_tenant(reg, "alice", "alicia")
    assert reg.execute("SELECT handle FROM user WHERE database_id=?", (i,)).fetchone()[0] == "alicia"
    registry.create_tenant(reg, "alice")


def test_registry_refuses_newer_version(home):
    registry.open_registry().close()
    c = sqlite3.connect(paths.registry_file())
    c.execute(f"PRAGMA user_version = {registry.REGISTRY_VERSION + 1}")
    c.close()
    with pytest.raises(registry.RegistryTooNewError):
        registry.open_registry()


def test_tenant_refused_per_file_if_newer(reg):
    from mtg_collector.db.connection import SchemaTooNewError
    from mtg_collector.db.schema import SCHEMA_VERSION
    i = registry.create_tenant(reg, "alice")
    c = sqlite3.connect(paths.tenant_db_file(i))
    c.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, 'now')", (SCHEMA_VERSION + 1,))
    c.commit()
    c.close()
    with pytest.raises(SchemaTooNewError):
        registry.migrate_tenant(i)


def test_adopt_copies_and_leaves_source(reg, tmp_path):
    from mtg_collector.db.schema import init_db
    src = tmp_path / "collection.sqlite"
    c = sqlite3.connect(src)
    init_db(c)
    c.execute("INSERT INTO settings (key, value) VALUES ('marker', 'x')")
    c.commit()
    c.close()
    i = registry.adopt_database(reg, "ryan", str(src))
    assert src.exists()
    t = sqlite3.connect(paths.tenant_db_file(i))
    assert t.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == "x"


def test_adopt_rejects_non_mtgc_file(reg, tmp_path):
    src = tmp_path / "other.sqlite"
    c = sqlite3.connect(src)
    c.execute("CREATE TABLE t (a)")
    c.commit()
    c.close()
    with pytest.raises(registry.RegistryError):
        registry.adopt_database(reg, "ryan", str(src))
    assert reg.execute("SELECT count(*) FROM user").fetchone()[0] == 0
    assert not list(paths.tenants_dir().glob("*.sqlite*"))


# --- key custody ---------------------------------------------------------

def test_key_round_trips_and_is_not_stored_in_clear(reg, home):
    i = registry.create_tenant(reg, "alice")
    secret = "sk-ant-SECRETSECRETSECRET"
    registry.set_tenant_key(reg, "alice", secret)
    assert registry.get_tenant_key(reg, i) == secret
    reg.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for f in home.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes(), f


def test_key_is_bound_to_its_tenant_and_master(reg, monkeypatch):
    a = registry.create_tenant(reg, "alice")
    b = registry.create_tenant(reg, "bob")
    registry.set_tenant_key(reg, "alice", "sk-one")
    blob = reg.execute("SELECT ciphertext FROM tenant_key WHERE database_id=?", (a,)).fetchone()[0]
    with pytest.raises(keycrypt.MasterKeyError):
        keycrypt.decrypt(blob, b, keycrypt.master_key())
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    with pytest.raises(keycrypt.MasterKeyError):
        registry.get_tenant_key(reg, a)


def test_set_key_without_master_key_refuses(reg, monkeypatch):
    registry.create_tenant(reg, "alice")
    monkeypatch.delenv("MTGC_MASTER_KEY")
    with pytest.raises(keycrypt.MasterKeyError):
        registry.set_tenant_key(reg, "alice", "sk-x")


def test_purge_removes_key(reg):
    i = registry.create_tenant(reg, "alice")
    registry.set_tenant_key(reg, "alice", "sk-x")
    registry.detach_tenant(reg, "alice")
    assert registry.get_tenant_key(reg, i) is None
    registry.purge_tenant(reg, "alice")
    assert reg.execute("SELECT count(*) FROM tenant_key").fetchone()[0] == 0


# --- CLI -----------------------------------------------------------------

def _mtg(home, *args, stdin=None):
    env = dict(os.environ, MTGC_HOME=str(home))
    return subprocess.run(
        [sys.executable, "-m", "mtg_collector", *args],
        env=env, input=stdin, capture_output=True, text=True, timeout=60,
    )


def test_cli_lifecycle_and_key_never_printed(home):
    secret = "sk-ant-CLISECRET"
    steps = [
        (("tenant", "create", "alice"), None),
        (("tenant", "identity", "add", "alice", "A@x.io"), None),
        (("tenant", "set-key", "alice"), secret + "\n"),
        (("tenant", "list"), None),
        (("tenant", "migrate", "--all"), None),
        (("tenant", "rename", "alice", "alicia"), None),
        (("tenant", "detach", "alicia"), None),
        (("tenant", "reattach", "alicia"), None),
        (("tenant", "detach", "alicia"), None),
        (("tenant", "purge", "alicia", "--confirm", "alicia"), None),
    ]
    for args, stdin in steps:
        r = _mtg(home, *args, stdin=stdin)
        assert r.returncode == 0, (args, r.stderr)
        assert secret not in r.stdout + r.stderr


def test_cli_purge_needs_matching_confirm(home):
    assert _mtg(home, "tenant", "create", "alice").returncode == 0
    assert _mtg(home, "tenant", "detach", "alice").returncode == 0
    r = _mtg(home, "tenant", "purge", "alice", "--confirm", "bob")
    assert r.returncode == 1 and "confirm" in r.stderr


def test_cli_migrate_requires_handle_or_all(home):
    assert _mtg(home, "tenant", "migrate").returncode != 0


def test_cli_error_is_nonzero(home):
    r = _mtg(home, "tenant", "detach", "nobody")
    assert r.returncode == 1 and "no active tenant" in r.stderr
