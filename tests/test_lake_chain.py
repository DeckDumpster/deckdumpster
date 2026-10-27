"""The lakehouse timer chain (lakehouse 14, K8): one clock, ordered links, arming
that refuses a part of it, and the retired timers gone."""

import os
import subprocess
from pathlib import Path

import pytest

from tests.subprocess_run import DEFAULT_TIMEOUT

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
CHAIN = ["mtgc-land", "mtgc-derive", "mtgc-prices", "mtgc-ship", "mtgc-value"]
RETIRED = ["mtgc-catalog-refresh", "mtgc-sealed-catalog", "mtgc-edhrec"]


def _lines(name, ext, key):
    return [ln for ln in (DEPLOY / f"{name}.{ext}").read_text().splitlines() if ln.startswith(key)]


@pytest.mark.parametrize("name", CHAIN)
def test_every_link_is_a_pair_on_the_one_clock_that_alerts_on_failure(name):
    assert _lines(name, "timer", "OnCalendar=") == ["OnCalendar=*-*-* 08:00:00 UTC"]
    assert "OnFailure=mtgc-alert-{{INSTANCE}}@%n.service" in (DEPLOY / f"{name}.service").read_text()
    assert _lines(name, "service", "ExecStart=") and all(
        ln.startswith("ExecStart=podman run --rm ") for ln in _lines(name, "service", "ExecStart=")
    ), "a chain link is a job container, never an exec into the server"


def test_each_link_is_ordered_after_the_previous():
    for prev, name in zip(CHAIN, CHAIN[1:]):
        after = _lines(name, "service", "After=")[0]
        assert f"{prev}-{{{{INSTANCE}}}}.service" in after
    assert "mtgc-" not in _lines(CHAIN[0], "service", "After=")[0]


@pytest.mark.parametrize("name", RETIRED)
def test_the_retired_timers_are_not_in_the_repo(name):
    assert not (DEPLOY / f"{name}.timer").exists()
    assert not (DEPLOY / f"{name}.service").exists()


def test_the_roles_are_split_by_zone():
    for name in ("mtgc-ship", "mtgc-value"):
        text = (DEPLOY / f"{name}.service").read_text()
        assert "AWS_PROFILE=mtgc-tenant" in text
    for name in ("mtgc-land", "mtgc-derive", "mtgc-prices"):
        assert "mtgc-tenant" not in (DEPLOY / f"{name}.service").read_text()
        assert "tenant-master.key" not in (DEPLOY / f"{name}.service").read_text()


def test_derive_touches_no_network_role():
    assert "AWS_PROFILE" not in (DEPLOY / "mtgc-derive.service").read_text()


# --- arming ---------------------------------------------------------------------

SYSTEMCTL = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
case "$*" in
  *is-enabled*) f="$STATE/$(echo "$*" | awk '{print $NF}')"; [ -e "$f" ] ;;
  *"enable --now"*) for t in "${@:4}"; do : > "$STATE/$t"; done ;;
esac
"""


@pytest.fixture
def host(tmp_path):
    home = tmp_path / "home"
    units = home / ".config/systemd/user"
    units.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (bin_dir / "systemctl").write_text(SYSTEMCTL)
    (bin_dir / "systemctl").chmod(0o755)
    conf = home / ".config/mtgc/inst"
    conf.mkdir(parents=True)
    (conf / "lake.env").write_text("MTGC_LAKE_S3_BUCKET=b\nMTGC_LAKE_TENANT_URI=s3://b/tenant\n")
    key = conf / "tenant-master.key"
    key.write_text("k")
    key.chmod(0o600)
    for name in CHAIN:
        for ext in ("service", "timer"):
            text = (DEPLOY / f"{name}.{ext}").read_text().replace("{{INSTANCE}}", "inst")
            (units / f"{name}-inst.{ext}").write_text(text)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "SYSTEMCTL_LOG": str(tmp_path / "log"), "STATE": str(state)}
    (tmp_path / "log").write_text("")

    class H:
        pass

    h = H()
    h.units, h.conf, h.key, h.state = units, conf, key, state
    h.log = lambda: (tmp_path / "log").read_text()
    h.chain = lambda *a: subprocess.run(
        ["bash", str(DEPLOY / "chain.sh"), *a], env=env, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
    return h


def test_arm_enables_all_five_together(host):
    r = host.chain("arm", "inst")
    assert r.returncode == 0, r.stderr
    enables = [ln for ln in host.log().splitlines() if "enable --now" in ln]
    assert len(enables) == 1
    assert all(f"{n}-inst.timer" in enables[0] for n in CHAIN)


@pytest.mark.parametrize("name", CHAIN)
def test_arm_refuses_an_unpaired_chain_and_enables_nothing(host, name):
    (host.units / f"{name}-inst.timer").unlink()
    r = host.chain("arm", "inst")
    assert r.returncode == 1
    assert f"{name}-inst.timer is not installed" in r.stderr
    assert "enable --now" not in host.log()


def test_arm_refuses_a_link_not_ordered_after_its_predecessor(host):
    svc = host.units / "mtgc-ship-inst.service"
    svc.write_text(svc.read_text().replace("mtgc-prices-inst.service", ""))
    r = host.chain("arm", "inst")
    assert r.returncode == 1 and "not After= mtgc-prices-inst.service" in r.stderr


def test_arm_refuses_while_a_retired_timer_is_on_the_host(host):
    (host.units / "mtgc-edhrec-inst.timer").write_text("")
    r = host.chain("arm", "inst")
    assert r.returncode == 1 and "retired mtgc-edhrec-inst.timer" in r.stderr


def test_arm_refuses_without_the_master_key_or_lake_config(host):
    host.key.chmod(0o644)
    (host.conf / "lake.env").write_text("#MTGC_LAKE_S3_BUCKET=\n")
    r = host.chain("arm", "inst")
    assert r.returncode == 1
    assert "mode 644" in r.stderr and "MTGC_LAKE_S3_BUCKET is not set" in r.stderr
    assert "enable --now" not in host.log()


def test_status_reports_a_half_armed_chain_as_a_failure(host):
    (host.state / "mtgc-land-inst.timer").write_text("")
    r = host.chain("status", "inst")
    assert r.returncode == 1 and "HALF ARMED" in r.stderr


def test_status_of_an_unarmed_whole_chain_is_ok(host):
    r = host.chain("status", "inst")
    assert r.returncode == 0, r.stderr
    assert "0/5" in r.stdout


@pytest.mark.parametrize("name", CHAIN)
def test_every_chain_container_carries_the_shared_catalogue(name):
    """sp-01eqhn: `lake value` died on 'MTGC_SHARED_DB is unset or missing' because only
    the app container had it. Every podman run of every link names the catalogue."""
    runs = [ln for ln in _lines(name, "service", "ExecStart=") if "podman run" in ln]
    assert runs
    for ln in runs:
        assert "-e MTGC_SHARED_DB=/data/shared.sqlite" in ln, ln
