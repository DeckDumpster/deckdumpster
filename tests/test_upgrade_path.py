"""The upgrade-path gate (sp-hvjyas): old layout -> split -> adopt -> ULID -> rollback -> again.

The served collection (what `collection_view` returns) is asserted identical at
every step, and the legacy file is asserted byte-identical throughout.
"""

import hashlib
import sqlite3
import sys

import pytest

from mtg_collector.db import registry
from mtg_collector.db.registry import RegistryError
from mtg_collector.db.schema import init_db, refresh_latest_prices, rebuild_fts
from mtg_collector.tenancy import keycrypt, paths, upgrade


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_DB", raising=False)
    monkeypatch.delenv("MTGC_SHARED_DB", raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    return tmp_path


def _monolith(path):
    c = sqlite3.connect(path)
    init_db(c)
    c.execute("INSERT INTO sets (set_code, set_name) VALUES ('tst', 'Test Set')")
    for i, (name, rar) in enumerate([("Alpha", "R"), ("Beta", "U"), ("Gamma", "C")], 1):
        c.execute("INSERT INTO cards (oracle_id, name, type_line) VALUES (?, ?, 'Instant')", (f"o{i}", name))
        c.execute(
            "INSERT INTO printings (printing_id, oracle_id, set_code, collector_number, rarity) "
            "VALUES (?, ?, 'tst', ?, ?)", (f"p{i}", f"o{i}", str(i), rar))
        c.execute("INSERT INTO prices (set_code, collector_number, source, price_type, price, observed_at) "
                  "VALUES ('tst', ?, 'tcgplayer', 'normal', ?, '2025-01-01T00:00:00')", (str(i), i * 1.5))
    refresh_latest_prices(c)
    rebuild_fts(c)
    for pid in ("p1", "p1", "p3"):
        c.execute("INSERT INTO collection (printing_id, finish, condition, status, acquired_at, source, card_name) "
                  "VALUES (?, 'nonfoil', 'Near Mint', 'owned', '2025-01-01T00:00:00.000Z', 'test', (SELECT card_name FROM printings WHERE printing_id=?))",
                  (pid, pid))
    c.commit()
    c.close()


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture
def legacy(home):
    p = str(home / "collection.sqlite")
    _monolith(p)
    return p


@pytest.fixture
def reg(home):
    c = registry.open_registry()
    yield c
    c.close()


def _served_tenant(database_id):
    return upgrade.collection_digest(str(paths.tenant_db_file(database_id)), str(paths.shared_file()))


def test_the_whole_upgrade_path(legacy, reg):
    before_bytes = _sha(legacy)
    served = upgrade.collection_digest(legacy)

    # split + adopt + migrate onto a ULID
    dbid, outcome = upgrade.migrate_legacy(reg, "ryan", legacy)
    assert outcome == "created"
    paths.validate_database_id(dbid)
    assert _served_tenant(dbid) == served
    assert _sha(legacy) == before_bytes
    t = sqlite3.connect(paths.tenant_db_file(dbid))
    names = {r[0] for r in t.execute("SELECT name FROM sqlite_master")}
    t.close()
    assert "collection" in names and "printings" not in names and "cards_fts" not in names

    # idempotent
    assert upgrade.migrate_legacy(reg, "ryan", legacy) == (dbid, "already")
    shared_sha = _sha(paths.shared_file())

    # rollback: unreachable, legacy untouched, serving the same
    assert upgrade.rollback_legacy(reg, "ryan") == (dbid, "detached")
    assert upgrade.rollback_legacy(reg, "ryan") == (dbid, "already")
    with pytest.raises(RegistryError):
        registry.find_tenant(reg, "ryan")
    assert upgrade.collection_digest(legacy) == served
    assert _sha(legacy) == before_bytes

    # again: a fresh ULID, same served collection, the shared catalogue not rewritten
    dbid2, outcome = upgrade.migrate_legacy(reg, "ryan", legacy)
    assert outcome == "created" and dbid2 != dbid
    assert _served_tenant(dbid2) == served
    assert _sha(paths.shared_file()) == shared_sha
    assert paths.tenant_db_file(dbid).exists()  # the first copy is retained, not purged


def test_split_deployment_uses_its_legacy_shared(home, reg):
    mono = str(home / "mono.sqlite")
    _monolith(mono)
    shared = str(home / "legacy-shared.sqlite")
    sqlite3.connect(mono).backup(sqlite3.connect(shared))
    # prune the user file the way `mtg db split --prune` does
    legacy = str(home / "collection.sqlite")
    sqlite3.connect(mono).backup(sqlite3.connect(legacy))
    c = sqlite3.connect(legacy)
    c.executescript("DELETE FROM printings; DELETE FROM cards; DELETE FROM sets;")
    c.commit(); c.close()
    served = upgrade.collection_digest(legacy, shared)
    dbid, _ = upgrade.migrate_legacy(reg, "ryan", legacy, legacy_shared=shared)
    assert _served_tenant(dbid) == served


def test_pruned_source_without_a_catalogue_is_refused(home, reg):
    legacy = str(home / "collection.sqlite")
    _monolith(legacy)
    c = sqlite3.connect(legacy)
    c.executescript("DELETE FROM printings; DELETE FROM cards; DELETE FROM sets;")
    c.commit(); c.close()
    with pytest.raises(RegistryError, match="no catalogue"):
        upgrade.migrate_legacy(reg, "ryan", legacy)
    assert not [r for r in registry.list_tenants(reg)]


def test_busy_source_is_refused_and_nothing_is_created(legacy, reg):
    holder = sqlite3.connect(legacy, timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(upgrade.BusyError):
            upgrade.migrate_legacy(reg, "ryan", legacy)
    finally:
        holder.execute("ROLLBACK"); holder.close()
    assert registry.list_tenants(reg) == []
    assert not paths.shared_file().exists()


def test_busy_tenant_refuses_rollback(legacy, reg):
    dbid, _ = upgrade.migrate_legacy(reg, "ryan", legacy)
    holder = sqlite3.connect(paths.tenant_db_file(dbid), timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(upgrade.BusyError):
            upgrade.rollback_legacy(reg, "ryan")
    finally:
        holder.execute("ROLLBACK"); holder.close()
    registry.find_tenant(reg, "ryan")


def test_a_failed_verification_leaves_no_reachable_tenant(legacy, reg, monkeypatch):
    real = upgrade.collection_digest
    calls = []
    monkeypatch.setattr(upgrade, "collection_digest", lambda *a, **k: (calls.append(1), real(*a, **k) + ("x" if len(calls) > 1 else ""))[1])
    with pytest.raises(RegistryError, match="differs"):
        upgrade.migrate_legacy(reg, "ryan", legacy)
    with pytest.raises(RegistryError):
        registry.find_tenant(reg, "ryan")
    (row,) = registry.list_tenants(reg)
    assert registry.state(row) == "purged" and not paths.tenant_db_file(row["database_id"]).exists()


def test_digest_control_arm_sees_a_changed_collection(legacy):
    a = upgrade.collection_digest(legacy)
    c = sqlite3.connect(legacy)
    c.execute("UPDATE collection SET status='sold' WHERE id=1"); c.commit(); c.close()
    assert upgrade.collection_digest(legacy) != a


def test_upgrade_tooling_is_never_a_startup_gate():
    import mtg_collector.cli.crack_pack_server as srv
    src = open(srv.__file__).read()
    assert "tenancy.upgrade" not in src and "legacy-migrate" not in src


def test_backups_are_not_touched_by_the_tooling():
    src = open(upgrade.__file__).read()
    for word in ("aws", "s3", "backup.sh", "shutil.copy"):
        assert word not in src.replace("src.backup(out)", "")


def test_cli_roundtrip(legacy, home):
    import subprocess
    env = {**__import__("os").environ, "MTGC_HOME": str(home), "MTGC_MASTER_KEY": keycrypt.generate_master_key()}
    def run(*a):
        return subprocess.run([sys.executable, "-m", "mtg_collector", "tenant", *a], env=env, capture_output=True, text=True)
    r = run("legacy-migrate", "ryan", legacy); assert r.returncode == 0, r.stderr
    assert "created" in r.stdout
    r = run("legacy-rollback", "ryan"); assert r.returncode == 0, r.stderr
