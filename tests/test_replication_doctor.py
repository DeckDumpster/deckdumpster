"""sp-5sq7wk: a multi-tenant deploy is not green while replication is not running,
and the litestream binary is installed only from the pinned, checksummed release."""

import io
import os
import subprocess
import tarfile
from pathlib import Path

from tests.subprocess_run import DEFAULT_TIMEOUT

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

# `systemctl --user <verb> [--quiet] <unit>`: a unit is up when its name is
# listed in $UP, one per line. Other verbs succeed and record nothing.
SYSTEMCTL = """#!/usr/bin/env bash
case "$2" in
  is-enabled|is-active) unit="${@: -1}"; grep -qx "$unit" "$UP" ;;
  *) exit 0 ;;
esac
"""

UNITS = [
    "mtgc-litestream-t.timer",
    "mtgc-litestream-check-t.timer",
    "mtgc-tenant-files-t.timer",
    "mtgc-litestream-t.service",
]


def _rig(tmp_path, up, with_binary=True, multitenant=True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "systemctl").write_text(SYSTEMCTL)
    (bin_dir / "systemctl").chmod(0o755)
    if with_binary:
        (bin_dir / "litestream").write_text("#!/bin/sh\n")
        (bin_dir / "litestream").chmod(0o755)
    home = tmp_path / "data"
    home.mkdir()
    if multitenant:
        (home / "registry.sqlite").write_bytes(b"")
    (tmp_path / "up").write_text("\n".join(up) + "\n")
    conf = tmp_path / "conf"
    conf.mkdir()
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "MTGC_LITESTREAM_HOME": str(home),
        "MTGC_CONFIG_DIR": str(conf),
        "UP": str(tmp_path / "up"),
    }


def _doctor(env, *args):
    return subprocess.run(
        ["bash", str(DEPLOY / "replication-doctor.sh"), *args, "t"],
        env=env, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
    )


def test_disabled_replication_fails_naming_the_unit(tmp_path):
    env = _rig(tmp_path, up=[u for u in UNITS if u != "mtgc-litestream-check-t.timer"])
    r = _doctor(env)
    assert r.returncode == 1
    assert "mtgc-litestream-check-t.timer" in r.stderr
    assert "mtgc-tenant-files-t.timer" not in r.stderr


def test_a_missing_binary_fails(tmp_path):
    r = _doctor(_rig(tmp_path, up=UNITS, with_binary=False))
    assert r.returncode == 1 and "litestream binary" in r.stderr


def test_everything_running_passes(tmp_path):
    r = _doctor(_rig(tmp_path, up=UNITS))
    assert r.returncode == 0, r.stderr


def test_a_single_tenant_instance_has_nothing_to_replicate(tmp_path):
    r = _doctor(_rig(tmp_path, up=[], multitenant=False))
    assert r.returncode == 0, r.stderr


def test_install_refuses_a_tarball_that_is_not_the_pinned_release(tmp_path):
    buf = io.BytesIO()
    body = b"#!/bin/sh\necho v0.5.17\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("litestream")
        info.size, info.mode = len(body), 0o755
        tf.addfile(info, io.BytesIO(body))
    srv = tmp_path / "srv"
    srv.mkdir()
    arch = "x86_64" if os.uname().machine == "x86_64" else "arm64"
    (srv / f"litestream-0.5.17-linux-{arch}.tar.gz").write_bytes(buf.getvalue())
    bin_dir = tmp_path / "out"
    r = subprocess.run(
        ["bash", str(DEPLOY / "litestream-install.sh")],
        env={**os.environ, "MTGC_LITESTREAM_BASE_URL": f"file://{srv}",
             "MTGC_LITESTREAM_BIN_DIR": str(bin_dir)},
        capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
    )
    assert r.returncode != 0 and "pinned sha256" in r.stderr
    assert not (bin_dir / "litestream").exists()
