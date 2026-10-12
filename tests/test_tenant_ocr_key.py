"""Bring-your-own-key OCR: whose key a job uses, and a pool fair across tenants."""

import sqlite3
import threading

import pytest

from mtg_collector.db import registry
from mtg_collector.tenancy import apikey, fairpool, keycrypt

A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
B = "01BX5ZZKBKACTAV9WEVGEMMVRY"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.delenv("MTGC_MULTITENANT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    return tmp_path


def test_single_tenant_uses_environment_key(home, monkeypatch):
    assert apikey.tenant_api_key(None) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert apikey.tenant_api_key(None) == "sk-env"


def test_tenant_uses_own_key_and_never_the_environment(home, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-host")
    conn = registry.open_registry()
    a = registry.create_tenant(conn, "alice")
    b = registry.create_tenant(conn, "bob")
    registry.set_tenant_key(conn, "alice", "sk-alice")
    conn.close()
    assert apikey.tenant_api_key(a) == "sk-alice"
    assert apikey.tenant_api_key(b) is None
    assert not apikey.has_tenant_api_key(b)


def test_key_never_in_tenant_file(home):
    conn = registry.open_registry()
    a = registry.create_tenant(conn, "alice")
    registry.set_tenant_key(conn, "alice", "sk-secret-alice")
    conn.close()
    from mtg_collector.tenancy import paths

    assert b"sk-secret-alice" not in paths.tenant_db_file(a).read_bytes()
    assert b"sk-secret-alice" not in (home / "registry.sqlite").read_bytes()


def _run_jobs(pool, plan):
    """plan: list of (tenant, name). Returns names in start order; each job blocks on its gate."""
    order, gates = [], {}
    lock = threading.Lock()

    def job(name):
        with lock:
            order.append(name)
        gates[name].wait(5)

    for _, name in plan:
        gates[name] = threading.Event()
    for tenant, name in plan:
        pool.submit(tenant, job, name)
    return order, gates


def _wait_for(pred):
    import time

    for _ in range(500):
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def test_one_tenants_burst_does_not_delay_another():
    pool = fairpool.FairPool(max_workers=4)
    plan = [("a", f"a{i}") for i in range(10)] + [("b", "b0")]
    order, gates = _run_jobs(pool, plan)
    _wait_for(lambda: "b0" in order)
    # a is capped at one in flight, so b's single job started while a0 still runs.
    assert order == ["a0", "b0"]
    for g in gates.values():
        g.set()
    assert pool.wait_idle(5)
    assert sorted(order) == sorted(n for _, n in plan)


def test_round_robin_between_tenants():
    pool = fairpool.FairPool(max_workers=1)
    hold = threading.Event()
    order = []
    pool.submit("z", hold.wait, 5)
    for tenant, name in [("a", "a0"), ("a", "a1"), ("a", "a2"), ("b", "b0"), ("b", "b1")]:
        pool.submit(tenant, order.append, name)
    hold.set()
    assert pool.wait_idle(5)
    assert order == ["a0", "b0", "a1", "b1", "a2"]


def test_one_tenants_failure_does_not_stop_the_pool(capfd):
    pool = fairpool.FairPool(max_workers=2)
    done = []

    def boom():
        raise RuntimeError("bad key")

    pool.submit("a", boom)
    pool.submit("b", done.append, "ok")
    pool.submit("a", done.append, "a-next")
    assert pool.wait_idle(5)
    assert sorted(done) == ["a-next", "ok"]
