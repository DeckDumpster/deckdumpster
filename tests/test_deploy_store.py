"""MTGC_STORE_ROOT: an opt-in alternate container store (de-3mo).

Rootless Podman's store lives under `$HOME`, which on the deployment box is the
disk prod runs from. `MTGC_STORE_ROOT` points non-prod container storage at
another filesystem via `--root`/`--runroot`.

Two properties carry the whole design, and both are tested here:

* **Unset is a strict no-op.** Prod never opts in, so prod's generated units and
  every podman call must come out exactly as they did before `deploy/store-lib.sh`
  existed. A host `store.env` that opts in must not change that either —
  `setup.sh` installs prod, and it honours the environment and nothing else.
* **The unit is the record.** An instance's Quadlet names the store it lives in,
  and `teardown.sh` / `prune-instances.sh` read it back, so they never remove the
  record while leaving the image and volume somewhere they can no longer be found.

These drive the real scripts with podman/systemd/loginctl stubbed out, so they
exercise the same code paths a deploy triggers. The podman stub logs its argv,
which is how "was this call scoped to the right store" is asserted.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = REPO_ROOT / "deploy"
SETUP = DEPLOY / "setup.sh"
TEARDOWN = DEPLOY / "teardown.sh"
PRUNE = DEPLOY / "prune-instances.sh"
STORE_TEARDOWN = DEPLOY / "store-teardown.sh"
STORE_LIB = DEPLOY / "store-lib.sh"

# Logs every invocation, then behaves like the stub in test_deploy_regeneration:
# `volume` fails so setup.sh does not splice in the shared reference volume.
# The store flags come first when a store is active, so they are shifted off
# before the subcommand is inspected.
PODMAN_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PODMAN_LOG"
while [ $# -gt 0 ]; do
    case "$1" in
        --root=*|--runroot=*) shift ;;
        *) break ;;
    esac
done
case "${1:-}" in
    volume) exit 1 ;;
    --version) echo "podman version 0.0.0-stub" ;;
esac
exit 0
"""

NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
LINGER_STUB = "#!/usr/bin/env bash\necho 'Linger=yes'\nexit 0\n"


class Host:
    """A fake box: stubbed podman/systemctl/loginctl and an empty $HOME."""

    def __init__(self, tmp_path, podman_stub=PODMAN_STUB):
        self.tmp_path = tmp_path
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        for name, body in (
            ("podman", podman_stub),
            ("systemctl", NOOP_STUB),
            ("loginctl", LINGER_STUB),
        ):
            stub = bin_dir / name
            stub.write_text(body)
            stub.chmod(0o755)

        self.home = tmp_path / "home"
        self.home.mkdir(exist_ok=True)
        self.log = tmp_path / "podman.log"
        self.log.write_text("")
        self.store = tmp_path / "store"

        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.env["XDG_RUNTIME_DIR"] = str(tmp_path / "run")
        self.env["PODMAN_LOG"] = str(self.log)
        # Inherited from the developer's own shell it would silently opt every
        # test into a real store.
        self.env.pop("MTGC_STORE_ROOT", None)
        self.env.pop("MTGC_STORE_GLOBAL_ARGS", None)

    def run(self, script, *args, store=None, check=True):
        env = dict(self.env)
        if store is not None:
            env["MTGC_STORE_ROOT"] = str(store)
        result = subprocess.run(
            ["bash", str(script), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        if check:
            assert result.returncode == 0, result.stdout + result.stderr
        return result

    def setup(self, *args, **kw):
        return self.run(SETUP, *args, **kw)

    def calls(self):
        return [ln for ln in self.log.read_text().splitlines() if ln]

    def quadlet(self, instance):
        return self.home / ".config/containers/systemd" / f"mtgc-{instance}.container"

    def service(self, prefix, instance):
        return self.home / ".config/systemd/user" / f"{prefix}-{instance}.service"

    def store_env(self):
        return self.home / ".config/mtgc/store.env"


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


# --- Unset means unchanged -------------------------------------------------


def test_unset_leaves_the_quadlet_without_a_store(host):
    """Prod never opts in, so prod's unit must carry no GlobalArgs at all."""
    host.setup("inst", "8083")

    assert "GlobalArgs" not in host.quadlet("inst").read_text()


def test_unset_leaves_every_podman_call_unflagged(host):
    host.setup("inst", "8083")

    assert host.calls(), "expected the stub to have recorded something"
    for call in host.calls():
        assert "--root=" not in call
        assert "--runroot=" not in call


def test_unset_leaves_the_timer_units_unflagged(host):
    host.setup("inst", "8083")

    text = host.service("mtgc-prices", "inst").read_text()
    assert "ExecStart=podman exec systemd-mtgc-inst mtg data fetch-prices --force" in text


def test_setup_ignores_a_store_env_that_opts_in(host):
    """THE PROD GUARANTEE. setup.sh installs prod, so a host config file does
    not get to decide where prod's volumes live — only the environment does."""
    conf = host.store_env()
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(f"MTGC_STORE_ROOT={host.store}\n")

    host.setup("inst", "8083")

    assert "GlobalArgs" not in host.quadlet("inst").read_text()
    for call in host.calls():
        assert "--root=" not in call


def test_setup_scaffolds_store_env_commented_out(host):
    """The knob is visible on a new box without changing anything."""
    host.setup("inst", "8083")

    text = host.store_env().read_text()
    assert "#MTGC_STORE_ROOT=" in text
    assert not any(
        line.startswith("MTGC_STORE_ROOT=") for line in text.splitlines()
    )


def test_setup_does_not_clobber_an_existing_store_env(host):
    conf = host.store_env()
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text("MTGC_STORE_ROOT=/somewhere/chosen\n")

    host.setup("inst", "8083")

    assert conf.read_text() == "MTGC_STORE_ROOT=/somewhere/chosen\n"


# --- Set means the store is used, everywhere -------------------------------


def _flags(host):
    graph = host.store / "storage"
    return [c for c in host.calls() if f"--root={graph} --runroot=" in c]


def test_set_stamps_the_quadlet_with_the_store(host):
    host.setup("inst", "8083", store=host.store)

    unit = host.quadlet("inst").read_text()
    line = next(ln for ln in unit.splitlines() if ln.startswith("GlobalArgs="))
    assert f"--root={host.store}/storage" in line
    assert "--runroot=" in line
    # systemd reads the unit top-down; the key has to be inside [Container].
    assert unit.index("[Container]") < unit.index("GlobalArgs=")
    assert unit.index("GlobalArgs=") < unit.index("[Service]")


def test_set_scopes_the_build_and_the_tag(host):
    host.setup("inst", "8083", store=host.store)

    scoped = _flags(host)
    assert any(" build " in c for c in scoped), host.calls()
    assert any(" tag " in c for c in scoped), host.calls()


def test_set_scopes_every_podman_call_after_activation(host):
    """A shim rather than an argument per call site, precisely so that missing
    one is impossible. `podman --version` runs before activation by design."""
    host.setup("inst", "8083", store=host.store)

    unscoped = [
        c for c in host.calls() if "--root=" not in c and not c.startswith("--version")
    ]
    assert unscoped == [], unscoped


def test_set_flags_the_timer_units(host):
    """systemd does not inherit our PATH, so the shim cannot reach them."""
    host.setup("inst", "8083", store=host.store)

    text = host.service("mtgc-prices", "inst").read_text()
    assert f"ExecStart=podman --root={host.store}/storage --runroot=" in text
    assert "mtg data fetch-prices --force" in text


def test_set_flags_podman_inside_the_edhrec_sh_wrapper(host):
    """mtgc-edhrec wraps two calls in `/bin/sh -c '...'`, so a line-anchored
    substitution would miss both."""
    host.setup("inst", "8083", store=host.store)

    text = host.service("mtgc-edhrec", "inst").read_text()
    assert text.count(f"podman --root={host.store}/storage") == 2


def test_the_backup_timer_has_no_podman_to_flag(host):
    """It runs backup.sh, which adopts the instance itself."""
    host.setup("inst", "8083", store=host.store)

    assert "--root=" not in host.service("mtgc-backup", "inst").read_text()


def test_the_runroot_is_keyed_to_the_graph_root(host):
    """Two stores sharing a runroot would drop each other's mount records, and
    prod is one of those stores."""
    other = host.tmp_path / "other-store"
    host.setup("a", "8083", store=host.store)
    host.setup("b", "8084", store=other)

    def runroot(instance):
        unit = host.quadlet(instance).read_text()
        line = next(ln for ln in unit.splitlines() if ln.startswith("GlobalArgs="))
        return line.split("--runroot=")[1].strip()

    assert runroot("a") != runroot("b")


def test_a_relative_store_root_is_refused(host):
    result = host.setup("inst", "8083", store="relative/dir", check=False)

    assert result.returncode != 0
    assert "must be an absolute path" in result.stdout + result.stderr


def test_a_store_root_with_shell_metacharacters_is_refused(host):
    """It is pasted into a systemd unit and a sed replacement; a truncated
    GlobalArgs would send systemd to the default store — prod's."""
    result = host.setup("inst", "8083", store="/tmp/a b|c", check=False)

    assert result.returncode != 0
    assert "may only contain" in result.stdout + result.stderr


def test_the_root_filesystem_is_refused_as_a_store(host):
    result = host.setup("inst", "8083", store="/", check=False)

    assert result.returncode != 0
    assert "must not be /" in result.stdout + result.stderr


# --- The unit is the record ------------------------------------------------


def test_an_existing_instance_keeps_the_store_it_was_created_in(host):
    """Re-running setup.sh is how unit changes reach an instance. It must not
    move the image and volume into whatever store the calling shell had."""
    host.setup("inst", "8083", store=host.store)
    original = host.quadlet("inst").read_text()

    host.setup("inst", "8083")  # no MTGC_STORE_ROOT this time

    assert host.quadlet("inst").read_text() == original


def test_teardown_removes_from_the_store_the_unit_names(host):
    """With no MTGC_STORE_ROOT in the environment at all."""
    host.setup("inst", "8083", store=host.store)
    host.log.write_text("")

    host.run(TEARDOWN, "inst", "--purge")

    graph = f"--root={host.store}/storage"
    assert any(graph in c and " rmi " in c for c in host.calls()), host.calls()
    assert any(graph in c and " volume rm " in c for c in host.calls()), host.calls()


def test_teardown_of_an_unstamped_instance_drops_an_inherited_store(host):
    """An unstamped unit is a statement, not a missing value. A shell that had
    activated a store, tearing down an instance that is not in one — CI cleaning
    up after itself — must fall back OUT of the store, not through it: aiming
    the removals at a store the instance was never in makes both no-op through
    their `|| true`, and then teardown deletes the unit, the only record of
    where the image and volume actually are."""
    host.setup("plain", "8083")
    host.log.write_text("")

    # Not `MTGC_STORE_ROOT=... bash teardown.sh`, which is an explicit decision
    # about this instance (below). This is a PARENT that activated: the shim is
    # on PATH, and that is an inherited store, which the unit outranks.
    result = subprocess.run(
        [
            "bash",
            "-c",
            f". {DEPLOY}/store-lib.sh && mtgc_store_activate "
            f"&& bash {TEARDOWN} plain --purge",
        ],
        capture_output=True,
        text=True,
        env={**host.env, "MTGC_STORE_ROOT": str(host.store)},
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    removals = [c for c in host.calls() if "rmi " in c or "volume rm " in c]
    assert removals, host.calls()
    for call in removals:
        assert "--root=" not in call, call


def test_an_explicit_store_overrides_a_missing_record(host):
    """The escape hatch for a unit that is wrong: an EXPLICIT variable with no
    shim on PATH is a decision about this instance, and still wins."""
    host.setup("inst", "8083")
    unit = host.quadlet("inst")
    unit.write_text(
        "\n".join(
            ln for ln in unit.read_text().splitlines() if not ln.startswith("GlobalArgs=")
        )
    )
    host.log.write_text("")

    host.run(TEARDOWN, "inst", "--purge", store=host.store)

    assert any(f"--root={host.store}/storage" in c for c in host.calls()), host.calls()


# --- prune-instances -------------------------------------------------------

# Reports a container as running only when the call carries the store flags, so
# an instance in an alternate store looks stopped to anything asking the default
# store. Discovery output is empty; the candidate comes from the Quadlet scan.
PRUNE_PODMAN_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PODMAN_LOG"
SCOPED=false
while [ $# -gt 0 ]; do
    case "$1" in
        --root=*|--runroot=*) SCOPED=true; shift ;;
        *) break ;;
    esac
done
case "${1:-}" in
    inspect) [ "$SCOPED" = "true" ] && echo "true" || echo "" ;;
    images|volume) ;;
esac
exit 0
"""


@pytest.fixture
def prune_host(tmp_path):
    return Host(tmp_path, podman_stub=PRUNE_PODMAN_STUB)


def test_prune_does_not_orphan_a_running_alternate_store_instance(prune_host):
    """The running-container check is what protects live instances. Asking the
    wrong store answers "not running", and the instance is then removed out from
    under itself."""
    prune_host.setup("inst", "8083", store=prune_host.store)
    prune_host.log.write_text("")

    result = prune_host.run(PRUNE)  # no MTGC_STORE_ROOT

    assert "inst (running)" in result.stdout, result.stdout
    assert prune_host.quadlet("inst").exists()
    assert not any(" rmi " in c for c in prune_host.calls())


def test_prune_removes_an_orphans_artifacts_before_its_unit(prune_host):
    """The unit is the only record of where the image and volume are."""
    prune_host.setup("inst", "8083", store=prune_host.store)
    # Nothing running: strip the flags so the stub reports "not running".
    stub = prune_host.tmp_path / "bin" / "podman"
    stub.write_text(PRUNE_PODMAN_STUB.replace('echo "true"', 'echo ""'))
    stub.chmod(0o755)
    prune_host.log.write_text("")

    prune_host.run(PRUNE)

    graph = f"--root={prune_host.store}/storage"
    assert any(graph in c and " rmi " in c for c in prune_host.calls()), prune_host.calls()
    assert any(
        graph in c and " volume rm " in c for c in prune_host.calls()
    ), prune_host.calls()
    assert not prune_host.quadlet("inst").exists()


# --- The rootless-netns repair ---------------------------------------------
#
# Podman 4.9 lets one rootless store's cleanup delete the scaffolding directory
# BOTH stores share, leaving the other holding a netns file that still looks
# valid and mounts into nothing — permanently, and silently. The repair drops
# our own store's stale netns name so podman rebuilds it.
#
# deckdumpster's Quadlet template sets no Network=, so nothing here creates that
# scaffolding today and a live run never reaches either branch. These drive the
# function directly, under the same `set -euo pipefail` every deploy script uses,
# because a guard that has never executed is a guard nobody has checked.


def _netns_case(host, scaffolding: bool):
    rundir = host.tmp_path / "run"
    script = f"""
        set -euo pipefail
        . {STORE_LIB}
        export XDG_RUNTIME_DIR={rundir}
        export MTGC_STORE_ROOT={host.store}
        mkdir -p "$XDG_RUNTIME_DIR/netns"
        touch "$XDG_RUNTIME_DIR/netns/$(mtgc_store_netns_name "$MTGC_STORE_ROOT/storage")"
        {'mkdir -p "$XDG_RUNTIME_DIR/libpod/tmp/rootless-netns/run/user/$(id -u)"'
         if scaffolding else ''}
        mtgc_store_netns_repair
        echo REACHED_THE_END
    """
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=host.env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REACHED_THE_END" in result.stdout, result.stdout + result.stderr
    return list((rundir / "netns").iterdir())


def test_a_stale_netns_is_dropped_when_the_scaffolding_is_gone(host):
    assert _netns_case(host, scaffolding=False) == []


def test_a_live_netns_is_left_alone(host):
    """The guard against being a live-namespace killer: scaffolding present
    means some store is using it, so nothing is removed. The function must still
    return cleanly — under `set -e` a bare `[ -d x ] && return 0` that takes the
    false branch is the kind of thing that kills the caller instead."""
    assert len(_netns_case(host, scaffolding=True)) == 1


# --- Removing a store ------------------------------------------------------


def test_store_teardown_refuses_without_a_store(host):
    """Podman's default store is prod's. Defaulting to it is the whole danger."""
    result = host.run(STORE_TEARDOWN, check=False)

    assert result.returncode != 0
    assert "No alternate container store configured" in result.stdout


def test_store_teardown_reads_the_host_store_env(host):
    """Unlike setup.sh: this command exists to remove a non-prod store, and the
    host config file is where the box says which one that is."""
    conf = host.store_env()
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(f"MTGC_STORE_ROOT={host.store}\n")

    result = host.run(STORE_TEARDOWN, check=False)

    assert f"Store to remove: {host.store}" in result.stdout


def test_store_teardown_scopes_every_removal(host):
    result = host.run(STORE_TEARDOWN, store=host.store)

    assert result.returncode == 0, result.stdout + result.stderr
    graph = f"--root={host.store}/storage"
    for verb in ("stop -a", "rm -af", "volume rm -af", "rmi -af", "network prune -f"):
        assert any(graph in c and verb in c for c in host.calls()), (verb, host.calls())
    assert not host.store.exists()


def test_no_script_runs_podman_system_reset():
    """It is not scoped by --root/--runroot. Aimed at a throwaway store it took
    prod down, taking user-global rootless state no flag pointed at. Removing a
    store is `rm -rf` on the paths, which is scoped by construction."""
    offenders = []
    scripts = sorted(DEPLOY.rglob("*.sh")) + sorted((REPO_ROOT / "tests").rglob("*.sh"))
    for path in scripts:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # store-lib.sh's header explains at length why not to
            if "system reset" in stripped:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {stripped}")
    assert offenders == [], offenders


def test_store_lib_is_sourced_by_every_deploy_script_that_runs_podman():
    """Missing one is the silent failure this whole mechanism exists to avoid.
    mac-*.sh are excluded: on macOS the store lives inside the podman machine
    VM, not in the host $HOME this is about."""
    for script in sorted(DEPLOY.glob("*.sh")):
        text = script.read_text()
        if script.name.startswith("mac-") or script.name == "store-lib.sh":
            continue
        runs_podman = any(
            line.strip().startswith("podman ") or " podman " in line
            for line in text.splitlines()
            if not line.strip().startswith("#")
        )
        if not runs_podman:
            continue
        assert "store-lib.sh" in text, f"{script.name} runs podman without store-lib.sh"
