"""The upgrade-path gate (sp-hvjyas): old layout -> split -> adopt -> ULID -> rollback -> again.

The served collection (what `collection_view` returns) is asserted identical at
every step, and the legacy file is asserted byte-identical throughout.
"""

import hashlib
import shutil
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


def test_too_little_free_space_is_refused_before_anything_is_written(legacy, reg, monkeypatch):
    real = shutil.disk_usage
    monkeypatch.setattr(upgrade.shutil, "disk_usage", lambda p: real(p)._replace(free=1024))
    with pytest.raises(RegistryError, match=r"needs \d+\.\d G, has 0\.0 G free on"):
        upgrade.migrate_legacy(reg, "ryan", legacy)
    assert not [r for r in registry.list_tenants(reg)]
    assert not paths.shared_file().exists()


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
        return subprocess.run([sys.executable, "-m", "mtg_collector", "tenant", *a], env=env, capture_output=True, text=True, timeout=120)
    r = run("legacy-migrate", "ryan", legacy); assert r.returncode == 0, r.stderr
    assert "created" in r.stdout
    r = run("legacy-rollback", "ryan"); assert r.returncode == 0, r.stderr


# --- Real-data drift (sp-63y52k) --------------------------------------------
# Prod's collection.sqlite (schema v53, 2026-10-14) was created before `sets.digital`
# existed; `_migrate_v26`-era ALTER TABLE appended it, so the deployed table reads
# (set_code, set_name, set_type, released_at, cards_fetched_at, digital, ...) while a
# fresh init_db declares digital *before* cards_fetched_at. A positional
# `INSERT ... SELECT *` then pours cards_fetched_at into digital: 37 prod sets carry a
# NULL cards_fetched_at, which failed `NOT NULL constraint failed: sets.digital`, and
# every other set would have had its digital flag and fetch timestamp swapped.

_LEGACY_SETS_DDL = """
CREATE TABLE sets (
    set_code TEXT PRIMARY KEY,
    set_name TEXT NOT NULL,
    set_type TEXT,
    released_at TEXT,
    cards_fetched_at TEXT
, digital INTEGER NOT NULL DEFAULT 0, base_set_size INTEGER, total_set_size INTEGER)
"""


def _with_legacy_sets_order(path):
    """Rebuild `sets` in the column order prod's ALTER-grown table has, rows intact."""
    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("PRAGMA legacy_alter_table = ON")  # leave collection_view pointing at `sets`
    c.execute("ALTER TABLE sets RENAME TO sets_fresh")
    c.execute(_LEGACY_SETS_DDL)
    c.execute("INSERT INTO sets (set_code, set_name, set_type, released_at, cards_fetched_at, digital, "
              "base_set_size, total_set_size) SELECT set_code, set_name, set_type, released_at, "
              "cards_fetched_at, digital, base_set_size, total_set_size FROM sets_fresh")
    c.execute("DROP TABLE sets_fresh")
    # one set never had its card list cached (NULL), one is digital-only and was
    c.execute("INSERT INTO sets (set_code, set_name, cards_fetched_at, digital) VALUES ('nul', 'Never Fetched', NULL, 0)")
    c.execute("INSERT INTO sets (set_code, set_name, cards_fetched_at, digital) "
              "VALUES ('dig', 'Digital Only', '2026-01-01T00:00:00Z', 1)")
    c.commit()
    c.close()


def _rows(path, table):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        return sorted((repr(sorted(dict(r).items())) for r in c.execute(f"SELECT * FROM [{table}]")))
    finally:
        c.close()


def test_prod_column_order_drift_copies_by_name(legacy, reg):
    _with_legacy_sets_order(legacy)
    before_bytes = _sha(legacy)
    served = upgrade.collection_digest(legacy)

    dbid, outcome = upgrade.migrate_legacy(reg, "ryan", legacy)
    assert outcome == "created"
    assert _served_tenant(dbid) == served
    assert _sha(legacy) == before_bytes
    # every value lands in the column of the same name, not the same position
    assert _rows(paths.shared_file(), "sets") == _rows(legacy, "sets")
    c = sqlite3.connect(paths.shared_file())
    assert c.execute("SELECT digital, cards_fetched_at FROM sets WHERE set_code='dig'").fetchone() == (1, "2026-01-01T00:00:00Z")
    assert c.execute("SELECT digital, cards_fetched_at FROM sets WHERE set_code='nul'").fetchone() == (0, None)
    c.close()


def test_every_shared_table_round_trips_with_counts(legacy, reg):
    from mtg_collector.db.schema import SHARED_TABLES
    _with_legacy_sets_order(legacy)
    lines = []
    upgrade.migrate_legacy(reg, "ryan", legacy, report=lines.append)
    for t in SHARED_TABLES:
        assert _rows(paths.shared_file(), t) == _rows(legacy, t), t
        assert any(line.split()[0] == t for line in lines), t


def test_a_null_in_a_not_null_column_with_a_default_takes_the_default(legacy, reg):
    # The shape the prod error message suggested: a legacy row whose NOT NULL column
    # holds NULL (possible in a table whose constraint was added later). The declared
    # default stands in for it, and the substitution is reported, never silent.
    c = sqlite3.connect(legacy)
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("PRAGMA legacy_alter_table = ON")  # leave collection_view pointing at `sets`
    c.execute("ALTER TABLE sets RENAME TO sets_fresh")
    c.execute(_LEGACY_SETS_DDL.replace("digital INTEGER NOT NULL DEFAULT 0", "digital INTEGER"))
    c.execute("INSERT INTO sets (set_code, set_name, set_type, released_at, cards_fetched_at, digital) "
              "SELECT set_code, set_name, set_type, released_at, cards_fetched_at, NULL FROM sets_fresh")
    c.execute("DROP TABLE sets_fresh")
    c.commit(); c.close()
    lines = []
    upgrade.migrate_legacy(reg, "ryan", legacy, report=lines.append)
    s = sqlite3.connect(paths.shared_file())
    assert s.execute("SELECT COUNT(*) FROM sets WHERE digital = 0").fetchone()[0] == 1
    s.close()
    assert any("sets.digital" in line and "default" in line for line in lines), lines


def test_an_empty_shared_file_is_treated_as_absent(legacy, reg):
    # Prod's volume carried a 0-byte shared.sqlite from an earlier experiment.
    paths.shared_file().write_bytes(b"")
    dbid, _ = upgrade.migrate_legacy(reg, "ryan", legacy)
    assert upgrade._count(str(paths.shared_file()), "printings") == 3
    assert _served_tenant(dbid) == upgrade.collection_digest(legacy)


def test_a_non_catalogue_shared_file_is_refused(legacy, reg):
    c = sqlite3.connect(paths.shared_file())
    c.execute("CREATE TABLE something_else (x)"); c.commit(); c.close()
    before = _sha(paths.shared_file())
    with pytest.raises(RegistryError, match="holds no catalogue"):
        upgrade.migrate_legacy(reg, "ryan", legacy)
    assert _sha(paths.shared_file()) == before
    assert registry.list_tenants(reg) == []
