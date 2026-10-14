"""Shipper and read-back (lakehouse 11): at-least-once, cursor after PUT, gap, zone_holdings."""

import os
import sqlite3

import pytest

from mtg_collector.db.schema import init_db
from mtg_collector.lake import crypto, holdings_outbox, shipper
from mtg_collector.lake import resolve as rs

A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
B = "01BX5ZZKBKACTAV9WEVGEMMVRY"
DAY = "2026-10-14"


@pytest.fixture
def key():
    return crypto.derive_key(os.urandom(32), A)


@pytest.fixture
def tenant():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = OFF")
    init_db(c)
    return c


@pytest.fixture
def state():
    return shipper.open_state(":memory:")


@pytest.fixture
def zone(tmp_path):
    return shipper.Zone(str(tmp_path / "zone"))


def _card(c, pid="p1", status="owned"):
    return c.execute(
        "INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
        "VALUES (?, 'nonfoil', '2026-01-01T00:00:00.000Z', 'manual', ?)", (pid, status)).lastrowid


def _ship(tenant, state, zone, key, **kw):
    tenant.commit()
    return shipper.ship_tenant(tenant, state, zone, A, key, as_of=DAY, **kw)


def test_ship_readback_and_three_numbers(tenant, state, zone, key):
    i = _card(tenant)
    j = _card(tenant, "p2")
    tenant.execute("UPDATE collection SET status = 'sold' WHERE id = ?", (i,))
    tenant.execute("DELETE FROM collection WHERE id = ?", (j,))
    tenant.execute("INSERT INTO sealed_collection (sealed_product_uuid, quantity, added_at) VALUES ('u', 2, 'd')")
    r = _ship(tenant, state, zone, key)
    assert (r.events, r.parts, r.gap) == (5, 1, None)
    b = shipper.readback_tenant(zone, state, A, key)
    assert (b.events, b.rows) == (5, 2)
    c = shipper.check_tenant(tenant, state, A)
    assert (c.outbox, c.shipped, c.read_back) == (5, 5, 5) and c.folded_equal and c.ok
    assert holdings_outbox.fold(tenant)["collection"].keys() == {i}


def test_nothing_plaintext_in_the_zone(tenant, state, zone, key, tmp_path):
    _card(tenant, "secretprinting")
    _ship(tenant, state, zone, key)
    for root, _, files in os.walk(tmp_path / "zone"):
        for f in files:
            assert b"secretprinting" not in open(os.path.join(root, f), "rb").read()


def test_cursor_moves_only_after_put(tenant, state, key):
    _card(tenant)
    tenant.commit()

    class Boom(shipper.Zone):
        def put(self, key, blob):
            raise OSError("PUT failed")

    z = Boom("/tmp")
    with pytest.raises(OSError):
        shipper.ship_tenant(tenant, state, z, A, key, as_of=DAY)
    assert shipper.cursor(state, A) == 0
    assert state.execute("SELECT COUNT(*) FROM ship_part").fetchone()[0] == 0


def test_crash_after_put_before_cursor_resends_same_object(tenant, state, zone, key):
    _card(tenant)
    tenant.commit()
    _ship(tenant, state, zone, key)
    keys1 = zone.list(rs.tenant_prefix(A))
    blob1 = zone.get(keys1[0])
    state.execute("DELETE FROM ship_cursor")          # the crash: PUT done, cursor lost
    state.execute("DELETE FROM ship_part")
    r = _ship(tenant, state, zone, key)
    assert r.events == 1
    assert zone.list(rs.tenant_prefix(A)) == keys1 and zone.get(keys1[0]) == blob1
    shipper.readback_tenant(zone, state, A, key)
    assert shipper.check_tenant(tenant, state, A).ok


def test_resend_on_another_day_doubles_events_and_changes_nothing(tenant, state, zone, key):
    _card(tenant)
    tenant.commit()
    shipper.ship_tenant(tenant, state, zone, A, key, as_of="2026-10-13")
    state.execute("DELETE FROM ship_cursor")
    shipper.ship_tenant(tenant, state, zone, A, key, as_of=DAY)
    assert len(zone.list(rs.tenant_prefix(A))) == 2
    b = shipper.readback_tenant(zone, state, A, key)
    assert (b.events, b.rows) == (1, 1)
    assert shipper.check_tenant(tenant, state, A).ok


def test_incremental_ships_only_past_cursor(tenant, state, zone, key):
    _card(tenant)
    _ship(tenant, state, zone, key)
    _card(tenant, "p2")
    r = _ship(tenant, state, zone, key)
    assert r.events == 1
    assert len(zone.list(rs.tenant_prefix(A))) == 2
    assert _ship(tenant, state, zone, key).events == 0


def test_batches(tenant, state, zone, key):
    for n in range(5):
        _card(tenant, f"p{n}")
    r = _ship(tenant, state, zone, key, batch=2)
    assert (r.events, r.parts) == (5, 3)
    shipper.readback_tenant(zone, state, A, key)
    assert shipper.check_tenant(tenant, state, A).ok


def test_gap_stops_the_shipper_and_is_recorded(tenant, state, zone, key):
    for n in range(4):
        _card(tenant, f"p{n}")
    tenant.execute("DELETE FROM holdings_outbox WHERE seq IN (2, 3)")
    r = _ship(tenant, state, zone, key)
    assert r.gap == (2, 3) and r.events == 1
    assert shipper.cursor(state, A) == 1
    assert shipper.open_gaps(state, A) == [(2, 3)]
    again = _ship(tenant, state, zone, key)           # never ships across it
    assert again.gap == (2, 3) and again.events == 0
    assert len(shipper.open_gaps(state, A)) == 1
    shipper.readback_tenant(zone, state, A, key)
    assert not shipper.check_tenant(tenant, state, A).ok


def test_gap_resolution_repairs_lost_delete(tenant, state, zone, key):
    i, j = _card(tenant), _card(tenant, "p2")
    _ship(tenant, state, zone, key)
    shipper.readback_tenant(zone, state, A, key)
    tenant.execute("DELETE FROM collection WHERE id = ?", (j,))
    tenant.execute("DELETE FROM holdings_outbox WHERE op = 'delete'")   # the lost delete
    _card(tenant, "p3")
    r = _ship(tenant, state, zone, key)
    assert r.gap and shipper.open_gaps(state, A)
    shipper.readback_tenant(zone, state, A, key)
    assert shipper.resolve_gap(tenant, state, A) > 0
    assert shipper.open_gaps(state, A) == []
    assert _ship(tenant, state, zone, key).gap is None
    b = shipper.readback_tenant(zone, state, A, key)
    assert b.rows == 2                                  # the ghost row is gone
    c = shipper.check_tenant(tenant, state, A)
    assert c.folded_equal and c.ok
    got = {r[0] for r in state.execute("SELECT row_id FROM zone_holdings")}
    assert j not in got and i in got


def test_resolve_requires_readback(tenant, state, zone, key):
    _card(tenant)
    _card(tenant, "p2")
    tenant.execute("DELETE FROM holdings_outbox WHERE seq = 1")
    r = _ship(tenant, state, zone, key)
    assert r.gap == (1, 1)
    _card(tenant, "p3")
    state.execute("INSERT INTO ship_part VALUES ('k', ?, 9, 9, 1, 'x')", (A,))
    with pytest.raises(shipper.ZoneError, match="read-back"):
        shipper.resolve_gap(tenant, state, A)


def test_readback_detects_a_lost_part(tenant, state, zone, key):
    for n in range(3):
        _card(tenant, f"p{n}")
    _ship(tenant, state, zone, key, batch=1)
    mid = [k for k in zone.list(rs.tenant_prefix(A)) if "part-seq-2-2" in k][0]
    os.remove(os.path.join(zone.root, mid))
    with pytest.raises(shipper.ZoneIncomplete, match="2-2"):
        shipper.readback_tenant(zone, state, A, key)


def test_readback_rejects_another_tenants_part_and_wrong_key(tenant, state, zone, key):
    _card(tenant)
    _ship(tenant, state, zone, key)
    with pytest.raises(crypto.LakeCryptoError):
        shipper.readback_tenant(zone, state, A, crypto.derive_key(os.urandom(32), A))
    src = zone.list(rs.tenant_prefix(A))[0]
    dst = src.replace(A, B)
    zone.put(dst, zone.get(src))                        # copied under another tenant
    with pytest.raises(crypto.LakeCryptoError):
        shipper.readback_tenant(zone, state, B, crypto.derive_key(os.urandom(32), B))


def test_backfill_once(tenant, state):
    tenant.execute("DROP TRIGGER holdings_outbox_collection_insert")
    _card(tenant)
    assert shipper.backfill(tenant, state, A) == 1
    with pytest.raises(shipper.ZoneError):
        shipper.backfill(tenant, state, A)
    assert shipper.backfill(tenant, state, A, again=True) == 1


def test_run_all_exit_codes(tmp_path, monkeypatch, zone):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path / "home"))
    from mtg_collector.db import registry
    from mtg_collector.lake import keys
    reg = registry.open_registry()
    reg.execute("INSERT INTO user (handle, database_id, created_at) VALUES ('a', ?, 'x')", (A,))
    reg.execute("INSERT INTO user (handle, database_id, created_at) VALUES ('b', ?, 'x')", (B,))
    master = os.urandom(32)
    keys.register(reg, A)
    keys.tombstone(reg, B, "gone")
    state = shipper.open_state(":memory:")
    t = sqlite3.connect(":memory:")
    init_db(t)
    t.execute("INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
              "VALUES ('p', 'nonfoil', 'x', 'm', 'owned')")
    t.commit()
    lines = []

    def run():
        return shipper.run_all(reg, state, zone, master=master, open_tenant=lambda i: t,
                               as_of=DAY, out=lines.append)

    class NoClose:
        def __getattr__(self, n):
            return getattr(t, n)

        def close(self):
            pass
    t_real, t = t, NoClose()
    assert run() == 0
    assert any("tombstoned" in x for x in lines)
    t_real.execute("INSERT INTO collection (printing_id, finish, acquired_at, source, status) "
                   "VALUES ('q', 'nonfoil', 'x', 'm', 'owned')")
    t_real.execute("DELETE FROM holdings_outbox WHERE seq = 2")
    t_real.commit()
    assert run() == shipper.EXIT_GAP
    reg.execute("DELETE FROM user WHERE database_id = ?", (B,))
    unregistered = "01CX5ZZKBKACTAV9WEVGEMMVRY"
    reg.execute("INSERT INTO user (handle, database_id, created_at) VALUES ('c', ?, 'x')", (unregistered,))
    state.execute("DELETE FROM ship_gap")
    state.execute("UPDATE ship_cursor SET shipped_through = 2")
    assert run() == shipper.EXIT_PARTIAL
