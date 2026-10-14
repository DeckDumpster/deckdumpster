"""mtg-erase (lakehouse 13): zone erase, proof, detach, purge, and its exit codes."""

import os

import pytest

from mtg_collector.db import registry
from mtg_collector.lake import crypto, erase, shipper
from mtg_collector.lake import keys as lake_keys
from mtg_collector.lake import resolve as rs
from mtg_collector.tenancy import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_DB", raising=False)
    monkeypatch.delenv("MTGC_SHARED_DB", raising=False)
    return tmp_path


@pytest.fixture
def world(home, tmp_path):
    reg = registry.open_registry()
    state = shipper.open_state(":memory:")
    zone = shipper.Zone(str(tmp_path / "zone"))
    gone = registry.create_tenant(reg, "gone")
    keep = registry.create_tenant(reg, "keep")
    master = os.urandom(32)
    for i in (gone, keep):
        lake_keys.register(reg, i)
        t = __import__("sqlite3").connect(str(paths.tenant_db_file(i)), isolation_level=None)
        t.execute("INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
                  "VALUES ('p1', 'nonfoil', '2026-01-01T00:00:00.000Z', 'manual', 'owned')")
        r = shipper.ship_tenant(t, state, zone, i, crypto.derive_key(master, i), as_of="2026-10-14")
        assert r.events == 1
        shipper.readback_tenant(zone, state, i, crypto.derive_key(master, i))
        t.close()
    yield reg, state, zone, gone, keep
    reg.close()


def _rows(state, i):
    return sum(state.execute(f"SELECT count(*) FROM {t} WHERE database_id = ?", (i,)).fetchone()[0]
               for t in erase._STATE_TABLES)


def test_erase_proves_empty_tombstones_detaches_and_purges(world):
    reg, state, zone, gone, keep = world
    assert zone.list(rs.tenant_prefix(gone))
    assert erase.erase(reg, state, zone, "gone", log=lambda *_: None) == erase.EXIT_OK
    assert zone.list(rs.tenant_prefix(gone)) == []
    assert lake_keys.state(reg, gone) == "tombstoned"
    assert _rows(state, gone) == 0
    row = reg.execute("SELECT * FROM user WHERE database_id = ?", (gone,)).fetchone()
    assert registry.state(row) == "purged"
    assert not paths.tenant_db_file(gone).exists()
    with pytest.raises(lake_keys.KeyTombstoned):
        lake_keys.lake_key(reg, gone, os.urandom(32))


def test_erase_leaves_other_tenants_alone(world):
    reg, state, zone, gone, keep = world
    erase.erase(reg, state, zone, "gone", log=lambda *_: None)
    assert zone.list(rs.tenant_prefix(keep))
    assert lake_keys.state(reg, keep) == "active"
    assert _rows(state, keep) > 0
    assert paths.tenant_db_file(keep).exists()


def test_unproven_erase_exits_3_and_detaches_nothing(world):
    reg, state, zone, gone, _ = world
    zone.delete = lambda key: None
    assert erase.erase(reg, state, zone, "gone", log=lambda *_: None) == erase.EXIT_UNPROVEN
    row = reg.execute("SELECT * FROM user WHERE database_id = ?", (gone,)).fetchone()
    assert registry.state(row) == "active"
    assert paths.tenant_db_file(gone).exists()
    assert _rows(state, gone) > 0


def test_rerun_after_completion_is_a_noop_success(world):
    reg, state, zone, *_ = world
    assert erase.erase(reg, state, zone, "gone", log=lambda *_: None) == 0
    assert erase.erase(reg, state, zone, "gone", log=lambda *_: None) == 0


def test_resumes_a_tenant_already_detached(world):
    reg, state, zone, gone, _ = world
    registry.detach_tenant(reg, "gone")
    assert erase.erase(reg, state, zone, "gone", log=lambda *_: None) == 0
    assert zone.list(rs.tenant_prefix(gone)) == []


def test_unknown_handle_is_exit_1(world, monkeypatch):
    with pytest.raises(SystemExit) as e:
        erase.main(["nobody", "--confirm", "nobody", "--dest", "/tmp/none"])
    assert e.value.code == erase.EXIT_ERROR


def test_confirm_must_repeat_the_handle(world):
    with pytest.raises(SystemExit) as e:
        erase.main(["gone", "--confirm", "other", "--dest", "/tmp/none"])
    assert e.value.code == erase.EXIT_ERROR
