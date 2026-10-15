"""Litestream backups (sp-sal0ci): config, per-tenant file sync, drill, check.

`aws` and `litestream` are PATH shims, as in test_backup_check.py: the aws shim
records argv and replays a listing; the litestream shim "restores" by copying a
file out of a local directory standing in for the bucket.
"""

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

T1 = "01J0000000000000000000000A"
T2 = "01J0000000000000000000000B"
T3 = "01J0000000000000000000000C"

AWS_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AWS_CALL_LOG"
case "$*" in
  *"s3 sync"*) case "$*" in *"${AWS_FAIL_ID:-@@none@@}"*) exit 1;; esac; exit 0;;
esac
cat "$AWS_STUB_OUT"
exit "${AWS_STUB_RC:-0}"
"""

# restore -o OUT s3://bucket/key  ->  cp $LS_REPLICA/key OUT
LITESTREAM_STUB = """#!/usr/bin/env bash
[ "$1" = restore ] || exit 2
out="$3"; url="$4"
key="${url#s3://*/}"; key="${key%%[?]*}"
[ -f "$LS_REPLICA/$key" ] || { echo "no replica for $key" >&2; exit 1; }
cp "$LS_REPLICA/$key" "$out"
"""


def make_db(path, version=1, rows=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS t (x)")
    for _ in range(rows):
        con.execute("INSERT INTO t VALUES (1)")
    con.execute(f"PRAGMA user_version = {version}")
    con.commit()
    con.close()


def make_registry(path, ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE user (handle TEXT, database_id TEXT, retired_at TEXT)")
    for i, db_id in enumerate(ids):
        con.execute("INSERT INTO user VALUES (?, ?, NULL)", (f"h{i}", db_id))
    con.commit()
    con.close()


@pytest.fixture
def env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("aws", AWS_STUB), ("litestream", LITESTREAM_STUB)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    home = tmp_path / "data"
    replica = tmp_path / "replica"
    (home / "tenants").mkdir(parents=True)
    replica.mkdir()
    (tmp_path / "aws.out").write_text("")
    (tmp_path / "aws.log").touch()
    conf = tmp_path / "conf"
    conf.mkdir()
    e = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MTGC_LITESTREAM_HOME": str(home),
        "MTGC_BACKUP_S3_BUCKET": "bkt",
        "MTGC_BACKUP_S3_REGION": "us-west-2",
        "MTGC_CONFIG_DIR": str(conf),
        "MTGC_STATE_DIR": str(tmp_path / "state"),
        "LS_REPLICA": str(replica),
        "AWS_CALL_LOG": str(tmp_path / "aws.log"),
        "AWS_STUB_OUT": str(tmp_path / "aws.out"),
    }
    e.pop("AWS_FAIL_ID", None)

    class Env:
        pass

    o = Env()
    o.tmp, o.home, o.replica, o.env = tmp_path, home, replica, e
    o.aws_log = tmp_path / "aws.log"
    o.aws_out = tmp_path / "aws.out"

    def run(script, *args, **extra):
        return subprocess.run(
            ["bash", str(DEPLOY / script), "t", *args],
            env={**e, **extra}, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
        )

    o.run = run
    return o


def seed_tenants(o, ids, replicate=True):
    make_registry(o.home / "registry.sqlite", ids)
    if replicate:
        make_registry(o.replica / "mtgc-t/litestream/registry", ids)
    for i in ids:
        make_db(o.home / "tenants" / f"{i}.sqlite")
        if replicate:
            make_db(o.replica / f"mtgc-t/litestream/tenants/{i}.sqlite")


# --- config -----------------------------------------------------------------

def test_config_replicates_registry_and_tenants_directory(env):
    r = env.run("litestream-config.sh")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert f"dir: {env.home}/tenants" in out and 'pattern: "*.sqlite"' in out
    assert "url: s3://bkt/mtgc-t/litestream/registry" in out
    assert "url: s3://bkt/mtgc-t/litestream/tenants" in out
    assert "shared.sqlite" not in out
    assert "tenants" in {p.name for p in env.home.iterdir()}


def test_config_names_the_region_on_every_replica(env):
    out = env.run("litestream-config.sh").stdout
    assert out.count("url: s3://") == 3
    assert out.count("region: us-west-2") == 3


def test_config_without_region_is_refused(env):
    r = env.run("litestream-config.sh", MTGC_BACKUP_S3_REGION="")
    assert r.returncode != 0 and "MTGC_BACKUP_S3_REGION" in r.stderr


def test_config_without_bucket_is_refused(env):
    r = env.run("litestream-config.sh", MTGC_BACKUP_S3_BUCKET="")
    assert r.returncode != 0 and "MTGC_BACKUP_S3_BUCKET" in r.stderr


# --- per-tenant file sync ---------------------------------------------------

def test_sync_is_keyed_by_database_id(env):
    seed_tenants(env, [T1, T2], replicate=False)
    (env.home / "tenant-files" / T1 / "source").mkdir(parents=True)
    (env.home / "tenant-files" / T2 / "source").mkdir(parents=True)
    r = env.run("tenant-files-sync.sh")
    assert r.returncode == 0, r.stderr
    log = env.aws_log.read_text()
    assert f"s3://bkt/mtgc-t/tenant-files/{T1}/" in log
    assert f"s3://bkt/mtgc-t/tenant-files/{T2}/" in log
    assert "--delete" not in log


def test_sync_ignores_directories_the_registry_does_not_name(env):
    seed_tenants(env, [T1], replicate=False)
    (env.home / "tenant-files" / T1).mkdir(parents=True)
    (env.home / "tenant-files" / T3).mkdir(parents=True)  # orphan / predecessor
    r = env.run("tenant-files-sync.sh")
    assert r.returncode == 0
    assert T3 not in env.aws_log.read_text()


def test_sync_one_failure_does_not_hide_or_stop_the_rest(env):
    seed_tenants(env, [T1, T2], replicate=False)
    for i in (T1, T2):
        (env.home / "tenant-files" / i).mkdir(parents=True)
    r = env.run("tenant-files-sync.sh", AWS_FAIL_ID=T1)
    assert r.returncode == 1
    assert f"FAILED for {T1}" in r.stderr
    assert T2 in env.aws_log.read_text()


@pytest.mark.parametrize("bad", ["../etc", T1.lower(), T1[:-1]])
def test_sync_refuses_a_malformed_id(env, bad):
    make_registry(env.home / "registry.sqlite", [bad])
    r = env.run("tenant-files-sync.sh")
    assert r.returncode != 0 and "malformed" in r.stderr
    assert env.aws_log.read_text() == ""


def test_sync_requires_the_registry(env):
    r = env.run("tenant-files-sync.sh")
    assert r.returncode != 0 and "registry not found" in r.stderr


# --- drill ------------------------------------------------------------------

def test_drill_restores_a_non_first_tenant_and_leaves_others_untouched(env):
    seed_tenants(env, [T1, T2, T3])
    r = env.run("litestream-drill.sh")
    assert r.returncode == 0, r.stderr
    assert T2 in r.stdout and "byte-identical" in r.stdout


def test_drill_fails_with_a_single_tenant(env):
    seed_tenants(env, [T1])
    r = env.run("litestream-drill.sh")
    assert r.returncode == 1 and "non-first tenant" in r.stderr


def test_drill_fails_when_the_tenant_replica_is_missing(env):
    seed_tenants(env, [T1, T2])
    (env.replica / f"mtgc-t/litestream/tenants/{T2}.sqlite").unlink()
    r = env.run("litestream-drill.sh")
    assert r.returncode == 1 and "could not restore tenant" in r.stderr


def test_drill_fails_on_a_corrupt_restore(env):
    seed_tenants(env, [T1, T2])
    (env.replica / f"mtgc-t/litestream/tenants/{T2}.sqlite").write_bytes(b"not a database" * 100)
    assert env.run("litestream-drill.sh").returncode == 1


# --- freshness check --------------------------------------------------------

LISTING = "2026-10-11T00:00:00+00:00\tmtgc-t/litestream/tenants/x/0001.ltx\n"


def test_check_fails_when_the_replica_is_empty(env):
    seed_tenants(env, [T1])
    r = env.run("litestream-check.sh")
    assert r.returncode == 1 and "NO objects" in r.stderr


def test_check_fails_when_list_fails(env):
    seed_tenants(env, [T1])
    r = env.run("litestream-check.sh", AWS_STUB_RC="255")
    assert r.returncode == 1 and "could not list" in r.stderr


def test_check_fails_when_restore_fails(env):
    seed_tenants(env, [T1], replicate=False)
    env.aws_out.write_text(LISTING)
    r = env.run("litestream-check.sh")
    assert r.returncode == 1 and "could not restore" in r.stderr


def test_check_passes_then_fails_when_position_does_not_advance(env):
    seed_tenants(env, [T1])
    env.aws_out.write_text(LISTING)
    first = env.run("litestream-check.sh")
    assert first.returncode == 0, first.stderr
    assert "OK" in first.stdout

    # Nothing written since: an idle database is not stale.
    assert env.run("litestream-check.sh").returncode == 0

    # Written since, replica unchanged: that is the failure.
    state = env.tmp / "state" / "litestream-t.position"
    os.utime(state, (1, 1))
    con = sqlite3.connect(env.home / "tenants" / f"{T1}.sqlite")
    con.execute("INSERT INTO t VALUES (2)")
    con.commit()
    con.close()
    third = env.run("litestream-check.sh")
    assert third.returncode == 1 and "did not advance" in third.stderr

    # Replica moves: green again.
    env.aws_out.write_text(LISTING + "2026-10-11T01:00:00+00:00\tmtgc-t/litestream/tenants/x/0002.ltx\n")
    assert env.run("litestream-check.sh").returncode == 0


def test_check_single_tenant_samples_the_collection_replica(env):
    make_db(env.home / "collection.sqlite")
    make_db(env.replica / "mtgc-t/litestream/collection")
    env.aws_out.write_text(LISTING)
    r = env.run("litestream-check.sh")
    assert r.returncode == 0, r.stderr
    assert "collection.sqlite" in r.stdout


# --- the unit's PATH (sp-fgve20) --------------------------------------------


def _run_sidecar(env, bin_dir):
    """litestream-run.sh under a PATH that, like the user manager's, lacks the install dir."""
    (bin_dir).mkdir(exist_ok=True)
    stub = bin_dir / "litestream"
    stub.write_text('#!/usr/bin/env bash\n[ "$1" = replicate ] && echo "replicating $*" && exit 0\nexit 2\n')
    stub.chmod(0o755)
    seed_tenants(env, [T1])
    system = "/usr/bin:/bin"
    return subprocess.run(
        ["bash", str(DEPLOY / "litestream-run.sh"), "t"],
        env={**env.env, "PATH": system, "MTGC_LITESTREAM_BIN_DIR": str(bin_dir)},
        capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
    )


def test_sidecar_finds_the_installed_binary_off_the_manager_path(env):
    r = _run_sidecar(env, env.tmp / "installed")
    assert r.returncode == 0, r.stderr
    assert "replicating" in r.stdout


def test_sidecar_without_the_binary_exits_78_so_the_unit_does_not_loop(env):
    seed_tenants(env, [T1])
    r = subprocess.run(
        ["bash", str(DEPLOY / "litestream-run.sh"), "t"],
        env={**env.env, "PATH": "/usr/bin:/bin", "MTGC_LITESTREAM_BIN_DIR": str(env.tmp / "empty")},
        capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
    )
    assert r.returncode == 78
    assert "litestream not found" in r.stderr
    unit = (DEPLOY / "mtgc-litestream.service").read_text()
    assert "RestartPreventExitStatus=78" in unit
