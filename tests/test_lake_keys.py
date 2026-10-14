"""Lake cipher, key derivation, tombstones and the resolution rule (lakehouse K7)."""

import argparse
import base64
import inspect
import io
import json
import os
import sqlite3

import pytest

from mtg_collector.cli import tenant_cmd
from mtg_collector.db import registry
from mtg_collector.lake import crypto, holdings_outbox, keys, resolve
from mtg_collector.tenancy import keycrypt

A = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
B = "01BX5ZZKBKACTAV9WEVGEMMVRY"


@pytest.fixture
def master():
    return os.urandom(32)


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    conn = registry.open_registry()
    yield conn
    conn.close()


# --- cipher --------------------------------------------------------------

def test_round_trip_and_determinism(master):
    k = crypto.derive_key(master, A)
    aad = resolve.range_part_key(A, "2026-10-14", 1, 5)
    blob = crypto.seal(b"holdings", k, aad)
    assert crypto.open_(blob, k, aad) == b"holdings"
    assert crypto.seal(b"holdings", k, aad) == blob          # a retry lands on the same bytes
    assert crypto.seal(b"holdings2", k, aad) != blob
    assert b"holdings" not in blob


def test_tamper_wrong_tenant_wrong_path_and_wrong_master_all_refuse(master):
    k = crypto.derive_key(master, A)
    aad = resolve.range_part_key(A, "2026-10-14", 1, 5)
    blob = crypto.seal(b"x" * 100, k, aad)
    for i in (0, 5, 20, len(blob) - 1):
        bad = bytearray(blob)
        bad[i] ^= 1
        with pytest.raises(crypto.LakeCryptoError):
            crypto.open_(bytes(bad), k, aad)
    with pytest.raises(crypto.LakeCryptoError):
        crypto.open_(blob, crypto.derive_key(master, B), aad)
    with pytest.raises(crypto.LakeCryptoError):
        crypto.open_(blob, k, resolve.range_part_key(A, "2026-10-14", 1, 6))
    with pytest.raises(crypto.LakeCryptoError):
        crypto.open_(blob, crypto.derive_key(os.urandom(32), A), aad)
    with pytest.raises(crypto.LakeCryptoError):
        crypto.open_(blob[:10], k, aad)


def test_derivation_is_per_tenant_and_stable(master):
    assert crypto.derive_key(master, A) == crypto.derive_key(master, A)
    assert crypto.derive_key(master, A) != crypto.derive_key(master, B)
    assert len(crypto.derive_key(master, A)) == 32
    assert crypto.fingerprint(crypto.derive_key(master, A)) != crypto.fingerprint(crypto.derive_key(master, B))


def test_master_key_file_must_be_mode_600_and_32_bytes(tmp_path):
    p = tmp_path / "tenant-master.key"
    p.write_text(crypto.generate_master_key())
    os.chmod(p, 0o644)
    with pytest.raises(crypto.LakeCryptoError, match="600"):
        crypto.load_master_key(str(p))
    os.chmod(p, 0o600)
    assert len(crypto.load_master_key(str(p))) == 32
    p.write_text(base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(crypto.LakeCryptoError):
        crypto.load_master_key(str(p))
    with pytest.raises(crypto.LakeCryptoError, match="does not exist"):
        crypto.load_master_key(str(tmp_path / "missing"))


# --- the lake key is not the BYO Anthropic key ---------------------------

def test_lake_key_is_separate_from_the_byo_anthropic_key(monkeypatch, tmp_path):
    byo_master = keycrypt.generate_master_key()
    monkeypatch.setenv("MTGC_MASTER_KEY", byo_master)
    monkeypatch.delenv(crypto.MASTER_KEY_FILE_ENV, raising=False)
    # Configuring the BYO master configures nothing for the lake.
    with pytest.raises(crypto.LakeCryptoError):
        crypto.master_key_path()
    assert crypto.MASTER_KEY_FILE_ENV not in ("MTGC_MASTER_KEY", "MTGC_MASTER_KEY_FILE")
    # The same 32 bytes used as each master yield unrelated keys: a BYO blob does
    # not open as a lake blob and the reverse.
    raw = base64.urlsafe_b64decode(byo_master)
    lake_blob = crypto.seal(b"s", crypto.derive_key(raw, A), "aad")
    byo_blob = keycrypt.encrypt(b"sk-ant", A, raw)
    with pytest.raises(crypto.LakeCryptoError):
        crypto.open_(byo_blob, crypto.derive_key(raw, A), "aad")
    with pytest.raises(keycrypt.MasterKeyError):
        keycrypt.decrypt(lake_blob, A, raw)
    # And neither module reaches for the other's secret.
    assert "MTGC_MASTER_KEY" not in inspect.getsource(crypto).replace("MTGC_LAKE_MASTER_KEY_FILE", "")
    assert "mtg_collector.lake" not in inspect.getsource(keycrypt)
    assert "tenant_key" not in inspect.getsource(keys).replace("lake_tenant_key", "")


# --- tombstones ----------------------------------------------------------

def test_unregistered_is_refused_registered_derives(reg, master):
    with pytest.raises(keys.KeyUnregistered):
        keys.lake_key(reg, A, master)
    keys.register(reg, A)
    keys.register(reg, A)  # idempotent
    assert keys.lake_key(reg, A, master) == crypto.derive_key(master, A)
    with pytest.raises(keys.KeyUnregistered):
        keys.lake_key(reg, B, master)


def test_a_tombstone_is_terminal_and_checked_before_the_master(reg, master):
    keys.register(reg, A)
    keys.register(reg, B)
    keys.tombstone(reg, A, "account deleted")
    keys.tombstone(reg, A, "again")  # idempotent
    with pytest.raises(keys.KeyTombstoned) as e:
        keys.lake_key(reg, A, master)
    assert e.value.deliberate_revocation
    with pytest.raises(keys.KeyTombstoned):
        keys.lake_key(reg, A, None)  # no master is needed to be refused
    with pytest.raises(keys.KeyTombstoned):
        keys.register(reg, A)
    assert keys.lake_key(reg, B, master)  # others unaffected
    # terminal in the schema, not only the code
    for sql in ("UPDATE lake_tenant_key SET state = 'active', tombstoned_at = NULL WHERE database_id = ?",
                "DELETE FROM lake_tenant_key WHERE database_id = ?"):
        with pytest.raises(sqlite3.DatabaseError):
            reg.execute(sql, (A,))
    assert keys.state(reg, A) == "tombstoned"


def test_only_a_tombstone_is_a_deliberate_revocation():
    assert keys.KeyTombstoned.deliberate_revocation
    assert not keys.KeyUnregistered.deliberate_revocation
    assert not keys.LakeKeyError.deliberate_revocation
    assert not crypto.LakeCryptoError("missing master").__dict__.get("deliberate_revocation", False)


def test_tombstoning_an_unregistered_id_still_records_it(reg):
    keys.tombstone(reg, A, "never shipped")
    assert keys.state(reg, A) == "tombstoned"


def test_purge_tombstones_the_lake_key(reg, monkeypatch):
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    i = registry.create_tenant(reg, "alice")
    keys.register(reg, i)
    registry.detach_tenant(reg, "alice")
    registry.purge_tenant(reg, "alice")
    assert keys.state(reg, i) == "tombstoned"


def test_lake_key_state_is_not_the_byo_key_row(reg, monkeypatch):
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    i = registry.create_tenant(reg, "alice")
    registry.set_tenant_key(reg, "alice", "sk-ant-x")
    assert keys.state(reg, i) is None
    keys.register(reg, i)
    assert registry.get_tenant_key(reg, i) == "sk-ant-x"
    assert reg.execute("SELECT count(*) FROM tenant_key").fetchone()[0] == 1


def test_registry_at_version_1_upgrades(tmp_path, monkeypatch):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    c = registry.open_registry()
    c.execute("DROP TRIGGER lake_tenant_key_no_delete")
    c.execute("DROP TRIGGER lake_tenant_key_terminal")
    c.execute("DROP TABLE lake_tenant_key")
    c.execute("PRAGMA user_version = 1")
    c.close()
    c = registry.open_registry()
    assert c.execute("PRAGMA user_version").fetchone()[0] == registry.REGISTRY_VERSION
    keys.register(c, A)


# --- the resolution rule -------------------------------------------------

EVENTS = [
    (1, "collection", 1, "upsert", json.dumps({"id": 1, "q": 1})),
    (2, "collection", 2, "upsert", json.dumps({"id": 2})),
    (3, "collection", 1, "upsert", json.dumps({"id": 1, "q": 2})),
    (4, "collection", 2, "delete", json.dumps({"id": 2})),
    (5, "sealed_collection", 9, "upsert", json.dumps({"id": 9})),
]


def test_highest_seq_wins_and_a_delete_leaves_nothing():
    out = resolve.resolve(EVENTS)
    assert out == {"collection": {1: {"id": 1, "q": 2}}, "sealed_collection": {9: {"id": 9}}}


def test_resolution_ignores_order_and_repetition():
    want = resolve.resolve(EVENTS)
    assert resolve.resolve(reversed(EVENTS)) == want
    assert resolve.resolve(EVENTS + EVENTS) == want


def test_unknown_op_is_refused():
    with pytest.raises(ValueError):
        resolve.resolve([(1, "collection", 1, "merge", "{}")])


def test_layout_is_one_prefix_per_tenant():
    k = resolve.range_part_key(A, "2026-10-14", 3, 9)
    assert k == f"tenant/database_id={A}/dataset=holdings/as_of=2026-10-14/part-seq-3-9.parquet.enc"
    assert k.startswith(resolve.tenant_prefix(A))
    assert resolve.database_id_of(k) == A
    for bad in ("raw/x", f"tenant/database_id={A.lower()}/x", "tenant/dataset=holdings/x"):
        with pytest.raises(ValueError):
            resolve.database_id_of(bad)
    with pytest.raises(ValueError):
        resolve.range_part_key(A, "2026-10-14", 9, 3)
    with pytest.raises(ValueError):
        resolve.tenant_prefix("../x")


def test_fold_is_the_resolution_rule():
    assert holdings_outbox.resolve is resolve.resolve


# --- the operator's verbs ------------------------------------------------

def _cli(monkeypatch, tmp_path, *argv, stdin=""):
    monkeypatch.setenv("MTGC_HOME", str(tmp_path))
    monkeypatch.setenv(crypto.MASTER_KEY_FILE_ENV, str(tmp_path / "tenant-master.key"))
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    ap = argparse.ArgumentParser()
    tenant_cmd.register(ap.add_subparsers())
    a = ap.parse_args(["tenant", *argv])
    a.func(a)


def test_cli_init_register_tombstone_status(monkeypatch, tmp_path, capsys):
    _cli(monkeypatch, tmp_path, "lake-key", "init")
    key = tmp_path / "tenant-master.key"
    assert (key.stat().st_mode & 0o777) == 0o600
    with pytest.raises(SystemExit):  # never overwritten
        _cli(monkeypatch, tmp_path, "lake-key", "init")
    c = registry.open_registry()
    monkeypatch.setenv("MTGC_MASTER_KEY", keycrypt.generate_master_key())
    i = registry.create_tenant(c, "alice")
    c.close()
    capsys.readouterr()
    with pytest.raises(SystemExit):
        _cli(monkeypatch, tmp_path, "lake-key", "backup")
    _cli(monkeypatch, tmp_path, "lake-key", "backup", "--yes")
    assert base64.urlsafe_b64decode(capsys.readouterr().out.strip()) == crypto.load_master_key(str(key))
    _cli(monkeypatch, tmp_path, "lake-key", "register", "--all")
    with pytest.raises(SystemExit):
        _cli(monkeypatch, tmp_path, "lake-key", "tombstone", i, "--reason", "x")
    _cli(monkeypatch, tmp_path, "lake-key", "tombstone", i, "--reason", "account deleted", "--yes")
    capsys.readouterr()
    _cli(monkeypatch, tmp_path, "lake-key", "status")
    out = capsys.readouterr().out
    assert f"{i}  tombstoned  account deleted" in out and "fingerprint" in out
